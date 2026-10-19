import pytest

from slo.budget import (
    BURN_RATE_ALERTS,
    allowed_downtime_minutes,
    budget_consumed_by_alert,
    budget_remaining,
    burn_rate,
    error_budget,
)


def test_error_budget():
    assert error_budget(0.999) == pytest.approx(0.001)


@pytest.mark.parametrize("bad", [0, 1, 1.5, -0.1])
def test_invalid_objective(bad):
    with pytest.raises(ValueError):
        error_budget(bad)


def test_allowed_downtime_999_is_43_minutes():
    # classic number: 99.9% over 30 days = 43.2 minutes
    assert allowed_downtime_minutes(0.999, 30) == pytest.approx(43.2)


def test_budget_remaining():
    assert budget_remaining(0.0, 0.999) == pytest.approx(1)
    assert budget_remaining(0.0005, 0.999) == pytest.approx(0.5)
    assert budget_remaining(0.002, 0.999) == pytest.approx(-1)  # slo broken


def test_burn_rate():
    assert burn_rate(0.001, 0.999) == pytest.approx(1)
    assert burn_rate(0.0144, 0.999) == pytest.approx(14.4)


def test_workbook_burn_rates_match_budget_percentages():
    # sanity check that I copied the numbers from the SRE workbook right
    expected = {"1h": 0.02, "6h": 0.05, "1d": 0.10, "3d": 0.10}
    hours = {"1h": 1, "6h": 6, "1d": 24, "3d": 72}
    for long_w, _short_w, factor, _sev in BURN_RATE_ALERTS:
        assert budget_consumed_by_alert(factor, hours[long_w]) == pytest.approx(expected[long_w])
