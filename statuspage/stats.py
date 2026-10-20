"""Calculations for the status page. Input = probe results from the data branch."""

import json
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

PROBE_EVERY_MIN = 5  # github actions cron, see .github/workflows/probe.yml


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def load_rows(data_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(Path(data_dir).glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_ts"] = parse_ts(row["ts"])
                rows.append(row)
    rows.sort(key=lambda r: r["_ts"])
    return rows


def availability(rows: list[dict]) -> float | None:
    """Good probes / all probes. Inconclusive ones (up=None) are ignored."""
    known = [r for r in rows if r["up"] is not None]
    if not known:
        return None
    return sum(r["up"] for r in known) / len(known)


def in_window(rows: list[dict], now: datetime, days: float) -> list[dict]:
    start = now - timedelta(days=days)
    return [r for r in rows if r["_ts"] > start]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1]


@dataclass
class Incident:
    start: datetime
    end: datetime | None  # None = still ongoing
    probes: int
    errors: set[str]

    def duration(self, now: datetime) -> timedelta:
        return (self.end or now) - self.start


def incidents(rows: list[dict]) -> list[Incident]:
    """Consecutive failed probes = one incident. Ends at the first good probe after."""
    result = []
    current = None
    for r in rows:
        if r["up"] is None:
            continue
        if not r["up"]:
            if current is None:
                current = Incident(start=r["_ts"], end=None, probes=0, errors=set())
            current.probes += 1
            current.errors.add(r.get("error") or f"HTTP {r.get('status')}")
        elif current is not None:
            current.end = r["_ts"]
            result.append(current)
            current = None
    if current is not None:
        result.append(current)
    return result


def daily(rows: list[dict], now: datetime, days: int = 30) -> list[dict]:
    """One entry per day (oldest first) with availability and latency."""
    today = now.astimezone(UTC).date()
    out = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        day_rows = [r for r in rows if r["_ts"].astimezone(UTC).date() == day]
        ms = [r["ms"] for r in day_rows if r["up"] and r.get("ms") is not None]
        out.append(
            {
                "day": day.isoformat(),
                "probes": len(day_rows),
                "availability": availability(day_rows),
                "p50_ms": percentile(ms, 50),
                "p95_ms": percentile(ms, 95),
            }
        )
    return out


def site_summary(
    rows: list[dict], now: datetime, objective: float = 0.999, latency_ms: float = 1500
) -> dict:
    last30 = in_window(rows, now, 30)
    known30 = [r for r in last30 if r["up"] is not None]
    bad30 = sum(1 for r in known30 if not r["up"])
    ms30 = [r["ms"] for r in last30 if r["up"] and r.get("ms") is not None]

    budget_used = None
    if known30:
        budget_used = (bad30 / len(known30)) / (1 - objective)

    # how much of the 30 days we actually have data for (cron runs get skipped sometimes)
    first = rows[0]["_ts"] if rows else now
    span_days = min(30, max((now - first).total_seconds() / 86400, 0))
    expected = span_days * 24 * 60 / PROBE_EVERY_MIN

    return {
        "last": rows[-1] if rows else None,
        "availability_24h": availability(in_window(rows, now, 1)),
        "availability_7d": availability(in_window(rows, now, 7)),
        "availability_30d": availability(last30),
        "budget_remaining": None if budget_used is None else 1 - budget_used,
        "p50_ms": percentile(ms30, 50),
        "p95_ms": percentile(ms30, 95),
        "fast_ratio": (sum(m < latency_ms for m in ms30) / len(ms30)) if ms30 else None,
        "probes_30d": len(last30),
        "coverage": (len(last30) / expected) if expected >= 1 else None,
        "data_days": span_days,
        "daily": daily(rows, now),
        "incidents": incidents(last30),
    }
