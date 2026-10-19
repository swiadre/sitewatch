from pathlib import Path

import yaml

from slo import rules

REPO = Path(__file__).parent.parent


def test_load_slos_applies_defaults():
    slos = rules.load_slos()
    assert len(slos) == 6  # 3 sites x (availability, latency)
    latency = [s for s in slos if s["slo"] == "latency"]
    assert all(s["threshold_seconds"] == 1.5 for s in latency)


def test_override(tmp_path):
    f = tmp_path / "slos.yaml"
    f.write_text(
        "defaults:\n  availability: {objective: 0.999}\n"
        "sites:\n  a: {}\n  b: {availability: {objective: 0.99}}\n"
    )
    slos = {s["site"]: s for s in rules.load_slos(f)}
    assert slos["a"]["objective"] == 0.999
    assert slos["b"]["objective"] == 0.99


def test_le_label_format():
    # has to match what prometheus_client exports
    assert rules.format_le(1) == "1.0"
    assert rules.format_le(1.5) == "1.5"


def test_impossible_page_condition_is_skipped():
    slo = {"site": "x", "slo": "latency", "objective": 0.9, "threshold_seconds": 1.5}
    fast = [a for a in rules.alert_rules(slo) if a["alert"] == "ErrorBudgetBurnFast"][0]
    assert "ratio_rate1h" not in fast["expr"]  # 14.4 * 0.1 > 1, can never fire
    assert "ratio_rate6h" in fast["expr"]


def test_generated_file_is_up_to_date(capsys):
    # if this fails: python -m slo.rules > deploy/prometheus/rules/slo.rules.yml
    rules.main()
    generated = capsys.readouterr().out
    committed = (REPO / "deploy/prometheus/rules/slo.rules.yml").read_text()
    assert generated == committed
    assert yaml.safe_load(generated)["groups"]


def test_min_events_guard():
    slo = {
        "site": "x",
        "slo": "availability",
        "objective": 0.999,
        "probe_interval_seconds": 30,
        "min_data_fraction": 0.5,
    }
    # 1h at one probe every 30s = 120 probes, need at least half
    assert rules.min_events(slo, "1h") == 60
    fast = [a for a in rules.alert_rules(slo) if a["alert"] == "ErrorBudgetBurnFast"][0]
    assert "slo:sli_events:increase1h" in fast["expr"]
    assert ">= 60" in fast["expr"]
