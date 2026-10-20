"""Summarize chaos/results/*.jsonl into a markdown table.

python -m chaos.report            # prints the table
python -m chaos.report --write    # also saves chaos/results/summary.md
"""

import json
import statistics
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def load(results_dir: Path = RESULTS_DIR) -> list[dict]:
    rows = []
    for f in sorted(results_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def fmt(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    if seconds >= 120:
        return f"{seconds / 60:.1f} min"
    return f"{seconds:.1f} s"


def stats(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    return statistics.mean(values), statistics.median(values), max(values)


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        # runs broken by something outside the test (e.g. my laptop went to sleep)
        # stay in the raw data with a reason, but don't count
        if r.get("invalid"):
            continue
        groups.setdefault((r["scenario"], r["mode"]), []).append(r)

    summary = []
    for (scenario, mode), runs in groups.items():
        mttd = [r["mttd_s"] for r in runs if r["mttd_s"] is not None]
        mttr = [r["mttr_s"] for r in runs if r["recovered"]]
        d_mean, d_med, _ = stats(mttd)
        r_mean, r_med, r_max = stats(mttr)
        # who fixed it: the remediator (its action) or nobody = kubernetes by itself
        fixers = {}
        for r in runs:
            if r["recovered"]:
                liveness = r.get("liveness_restart_s")
                if liveness is not None and liveness <= (r.get("action_at_s") or 1e9):
                    # the k8s livenessProbe restarted the app before the remediator acted
                    # (from the kubelet event, see chaos/k8s_events.py)
                    who = "k8s livenessProbe"
                elif r.get("no_failed_check"):
                    who = "no visible downtime"
                elif r.get("action"):
                    who = r["action"]
                else:
                    who = "kubernetes itself"
                fixers[who] = fixers.get(who, 0) + 1
        summary.append(
            {
                "scenario": scenario,
                "mode": mode,
                "runs": len(runs),
                "recovered": sum(r["recovered"] for r in runs),
                "detected": len(mttd),
                "mttd_mean": d_mean,
                "mttd_median": d_med,
                "mttr_mean": r_mean,
                "mttr_median": r_med,
                "mttr_max": r_max,
                "fixed_by": ", ".join(f"{k} {v}×" for k, v in sorted(fixers.items())),
            }
        )
    order = ["kill", "hang", "latency", "disk", "bad_deploy"]
    summary.sort(
        key=lambda s: (order.index(s["scenario"]) if s["scenario"] in order else 99, s["mode"])
    )
    return summary


def to_markdown(summary: list[dict]) -> str:
    lines = [
        "| scenario | mode | runs | recovered | MTTD mean | MTTD median "
        "| MTTR mean | MTTR median | MTTR max | fixed by |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in summary:
        lines.append(
            f"| {s['scenario']} | {s['mode']} | {s['runs']} | {s['recovered']}/{s['runs']} "
            f"| {fmt(s['mttd_mean'])} | {fmt(s['mttd_median'])} | {fmt(s['mttr_mean'])} "
            f"| {fmt(s['mttr_median'])} | {fmt(s['mttr_max'])} | {s['fixed_by']} |"
        )
    return "\n".join(lines)


def main() -> None:
    results_dir = RESULTS_DIR / "k8s" if "--k8s" in sys.argv else RESULTS_DIR
    table = to_markdown(summarize(load(results_dir)))
    print(table)
    if "--write" in sys.argv:
        (results_dir / "summary.md").write_text(table + "\n")


if __name__ == "__main__":
    main()
