"""Error budget math. Everything here is plain functions so it's easy to test."""

# (long window, short window, burn rate factor, severity)
# from the SRE workbook, chapter "Alerting on SLOs", for a 30 day SLO window
BURN_RATE_ALERTS = [
    ("1h", "5m", 14.4, "page"),  # 2% of the budget gone in 1 hour
    ("6h", "30m", 6, "page"),  # 5% of the budget gone in 6 hours
    ("1d", "2h", 3, "ticket"),  # 10% of the budget gone in 1 day
    ("3d", "6h", 1, "ticket"),  # 10% of the budget gone in 3 days
]


def error_budget(objective: float) -> float:
    """Allowed fraction of bad events, e.g. 0.999 -> 0.001"""
    if not 0 < objective < 1:
        raise ValueError(f"objective must be between 0 and 1, got {objective}")
    return 1 - objective


def allowed_downtime_minutes(objective: float, window_days: int = 30) -> float:
    """How many minutes of full downtime fit in the budget."""
    return error_budget(objective) * window_days * 24 * 60


def budget_remaining(error_ratio: float, objective: float) -> float:
    """Fraction of the error budget left (1 = untouched, 0 = used up, <0 = SLO broken)."""
    return 1 - error_ratio / error_budget(objective)


def burn_rate(error_ratio: float, objective: float) -> float:
    """How fast we burn the budget. 1 = we'd use exactly the whole budget in the window."""
    return error_ratio / error_budget(objective)


def budget_consumed_by_alert(factor: float, long_window_hours: float, window_days: int = 30):
    """Fraction of the budget used before an alert with this burn rate fires.

    e.g. 14.4x for 1h over 30 days -> 14.4 * 1 / 720 = 0.02 (2%)
    """
    return factor * long_window_hours / (window_days * 24)
