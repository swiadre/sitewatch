from datetime import UTC, datetime, timedelta

from statuspage.stats import availability, daily, incidents, percentile, site_summary

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def row(minutes_ago, up, ms=300, error=None):
    ts = NOW - timedelta(minutes=minutes_ago)
    return {
        "ts": ts.isoformat(),
        "_ts": ts,
        "site": "s",
        "up": up,
        "ms": ms if up else None,
        "status": 200 if up else 503,
        "error": error,
    }


def test_availability_ignores_inconclusive():
    rows = [row(10, True), row(5, False), row(1, None)]
    assert availability(rows) == 0.5
    assert availability([row(1, None)]) is None


def test_incidents():
    rows = [row(30, True), row(25, False), row(20, False), row(15, True), row(10, False)]
    inc = incidents(rows)
    assert len(inc) == 2
    assert inc[0].probes == 2
    assert inc[0].duration(NOW) == timedelta(minutes=10)  # 25 min ago -> 15 min ago
    assert inc[1].end is None  # still down
    assert inc[1].duration(NOW) == timedelta(minutes=10)


def test_inconclusive_does_not_end_an_incident():
    rows = [row(20, False), row(15, None), row(10, False), row(5, True)]
    (inc,) = incidents(rows)
    assert inc.probes == 2


def test_daily_has_30_days_oldest_first():
    days = daily([row(5, True)], NOW)
    assert len(days) == 30
    assert days[-1]["day"] == "2026-10-20"
    assert days[-1]["availability"] == 1
    assert days[0]["probes"] == 0


def test_percentile():
    assert percentile([], 95) is None
    assert percentile([100], 95) == 100
    assert percentile(list(range(1, 101)), 50) == 50.5


def test_site_summary_budget():
    # 1 bad out of 1000 = exactly the 99.9% budget
    rows = [row(i, i != 500) for i in range(1000, 0, -1)]
    s = site_summary(rows, NOW)
    assert round(s["budget_remaining"], 6) == 0
    assert s["availability_30d"] == 0.999
