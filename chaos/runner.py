"""Runs a chaos scenario N times and measures MTTD and MTTR.

    python -m chaos.runner kill --runs 10 --mode auto
    python -m chaos.runner hang --runs 5 --mode manual     # you fix it by hand

MTTD = fault injected -> alert received by the remediator (= also sent to telegram)
MTTR = fault injected -> demo app healthy again (3 good checks in a row, measured from here)

Results are appended to chaos/results/<scenario>-<mode>.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

from chaos.scenarios import DEMO_URL, REMEDIATOR, SCENARIOS, TARGET, Scenario

PROMETHEUS = "http://localhost:9092" if TARGET == "k8s" else "http://localhost:9090"
RESULTS_DIR = Path(__file__).parent / "results" / ("k8s" if TARGET == "k8s" else "")
CHECK_EVERY = 0.5
# if not a single check failed this long after the fault, the app was never visibly down
# (happens in k8s: a deleted pod is replaced faster than we check)
NO_IMPACT_AFTER = 60
HEALTHY_STREAK = 3
MAX_LATENCY = 1.0  # same threshold as the DemoSlow alert


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def demo_healthy(client: httpx.Client) -> bool:
    try:
        r = client.get(DEMO_URL + "/", timeout=2)
    except httpx.HTTPError:
        return False
    return (
        r.status_code == 200
        and "sitewatch demo app" in r.text
        and r.elapsed.total_seconds() < MAX_LATENCY
    )


def wait_until(cond, timeout: float, what: str, every: float = 2) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(every)
    log(f"timeout waiting for: {what}")
    return False


def demo_alerts_active(client: httpx.Client) -> list[str]:
    """Pending or firing Demo* alerts in prometheus."""
    r = client.get(f"{PROMETHEUS}/api/v1/query", params={"query": 'ALERTS{alertname=~"Demo.*"}'})
    return [x["metric"]["alertname"] for x in r.json()["data"]["result"]]


def reset_demo(client: httpx.Client) -> None:
    """Get the demo app back to a known good state (version 1.0, no faults)."""
    for s in SCENARIOS.values():
        s.cleanup()
    status = client.get(f"{REMEDIATOR}/status").json()
    if status["version"] != "1.0":
        log(f"demo is on {status['version']}, deploying 1.0")
        client.post(f"{REMEDIATOR}/deploy", json={"version": "1.0"}, timeout=120)


def wait_for_steady_state(client: httpx.Client) -> None:
    def healthy_streak():
        return all(demo_healthy(client) for _ in range(HEALTHY_STREAK))

    if not wait_until(healthy_streak, 60, "demo healthy"):
        reset_demo(client)
        if not wait_until(healthy_streak, 120, "demo healthy after reset"):
            sys.exit("demo app doesn't get healthy, giving up")

    # old alerts must be gone, otherwise alertmanager won't send a new "firing" for the
    # same group and the next run would never get detected
    wait_until(lambda: not demo_alerts_active(client), 600, "old demo alerts to resolve", 5)
    time.sleep(70)  # alertmanager group_interval is 1m, let the "resolved" go through


def first_event(events: list[dict], type: str, alertnames: list[str]) -> dict | None:
    for e in events:
        if e["type"] == type and e.get("alertname") in alertnames:
            return e
    return None


def run_once(client: httpx.Client, scenario: Scenario, mode: str, timeout: float) -> dict:
    client.post(f"{REMEDIATOR}/auto", json={"enabled": mode == "auto"})

    t0 = time.time()
    scenario.inject()
    log(f"injected '{scenario.name}'")

    went_down_at = recovered_at = detected_at = None
    streak_start, streak = None, 0
    told_human = False
    no_failed_check = False

    while time.time() - t0 < timeout:
        if went_down_at is None and time.time() - t0 > NO_IMPACT_AFTER:
            no_failed_check = True
            break

        ok = demo_healthy(client)
        now = time.time()

        if not ok:
            streak = 0
            if went_down_at is None:
                went_down_at = now
        elif went_down_at is not None:
            if streak == 0:
                streak_start = now
            streak += 1
            if streak >= HEALTHY_STREAK:
                recovered_at = streak_start
                break

        if detected_at is None:
            events = client.get(f"{REMEDIATOR}/events", params={"since": t0}).json()
            ev = first_event(events, "alert_firing", scenario.alerts)
            if ev:
                detected_at = ev["ts"]
                log(f"detected by {ev['alertname']} after {detected_at - t0:.1f}s")

        if mode == "manual" and detected_at and not told_human:
            log("=" * 60)
            log("ALERT! fix it by hand now:")
            log(f"    {scenario.manual_fix}")
            log("=" * 60)
            print("\a", end="", flush=True)
            told_human = True

        time.sleep(CHECK_EVERY)

    events = client.get(f"{REMEDIATOR}/events", params={"since": t0}).json()
    action = first_event(events, "action_done", scenario.alerts)
    if detected_at is None:
        ev = first_event(events, "alert_firing", scenario.alerts)
        detected_at = ev["ts"] if ev else None

    result = {
        "scenario": scenario.name,
        "mode": mode,
        "t0": t0,
        "went_down_s": round(went_down_at - t0, 2) if went_down_at else None,
        "mttd_s": round(detected_at - t0, 2) if detected_at else None,
        "mttr_s": 0.0
        if no_failed_check
        else (round(recovered_at - t0, 2) if recovered_at else None),
        "recovered": no_failed_check or recovered_at is not None,
        # true = no check ever failed (checks every 0.5 s, so a shorter blip could be missed)
        "no_failed_check": no_failed_check,
        "action": action["action"] if action else None,
        "action_at_s": round(action["ts"] - t0, 2) if action else None,
    }
    scenario.cleanup()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=list(SCENARIOS) + ["all"])
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
    parser.add_argument("--timeout", type=float, default=None, help="max seconds per run")
    args = parser.parse_args()

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    timeout = args.timeout or (300 if args.mode == "auto" else 1800)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=10) as client:
        for name in names:
            scenario = SCENARIOS[name]
            out = RESULTS_DIR / f"{name}-{args.mode}.jsonl"
            for i in range(1, args.runs + 1):
                log(f"--- {name} ({args.mode}) run {i}/{args.runs}: {scenario.description}")
                wait_for_steady_state(client)
                result = run_once(client, scenario, args.mode, timeout)
                result["run"] = i
                with open(out, "a") as f:
                    f.write(json.dumps(result) + "\n")
                log(
                    f"result: MTTD={result['mttd_s']}s MTTR={result['mttr_s']}s "
                    f"action={result['action']}"
                )

        # leave auto-remediation on when done
        client.post(f"{REMEDIATOR}/auto", json={"enabled": True})


if __name__ == "__main__":
    main()
