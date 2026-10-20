"""Finds out if Kubernetes itself fixed something during a chaos run (k8s target only).

The kubelet writes an event "Container demo failed liveness probe, will be restarted"
when the livenessProbe restarts the container. Comparing timestamps of the app coming back
and the remediator's action isn't reliable (both happen within a second), the event is.

    python -m chaos.k8s_events chaos/results/k8s/hang-auto.jsonl   # add it to old results

k8s only keeps events for ~1 hour, so run it soon after the runs.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def liveness_restart_times() -> list[float]:
    out = subprocess.run(
        ["kubectl", "-n", "sitewatch", "get", "events", "-o", "json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    times = []
    for ev in json.loads(out)["items"]:
        if ev.get("reason") == "Killing" and "liveness" in (ev.get("message") or ""):
            ts = ev.get("firstTimestamp") or ev.get("eventTime")
            times.append(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    return sorted(times)


def liveness_restart_after(t0: float, until: float, times: list[float]) -> float | None:
    """Seconds after t0 of the first liveness restart in [t0, until], or None."""
    for t in times:
        if t0 <= t <= until:
            return round(t - t0, 2)
    return None


def backfill(path: Path) -> None:
    times = liveness_restart_times()
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for r in rows:
        until = r["t0"] + (r.get("mttr_s") or 300) + 5
        r["liveness_restart_s"] = liveness_restart_after(r["t0"], until, times)
        print(r["run"], "liveness restart at", r["liveness_restart_s"])
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    backfill(Path(sys.argv[1]))
