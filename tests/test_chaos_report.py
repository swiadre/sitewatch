import json

from chaos.report import fmt, load, summarize, to_markdown
from chaos.runner import first_event


def write(tmp_path, name, rows):
    (tmp_path / name).write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def row(scenario, mode, mttd, mttr):
    return {
        "scenario": scenario,
        "mode": mode,
        "mttd_s": mttd,
        "mttr_s": mttr,
        "recovered": mttr is not None,
    }


def test_summary(tmp_path):
    write(tmp_path, "kill-auto.jsonl", [row("kill", "auto", 20, 25), row("kill", "auto", 30, 35)])
    write(tmp_path, "kill-manual.jsonl", [row("kill", "manual", 20, None)])
    summary = summarize(load(tmp_path))

    auto = [s for s in summary if s["mode"] == "auto"][0]
    assert auto["runs"] == 2
    assert auto["mttd_mean"] == 25
    assert auto["mttr_mean"] == 30
    assert auto["mttr_max"] == 35

    manual = [s for s in summary if s["mode"] == "manual"][0]
    assert manual["recovered"] == 0
    assert manual["mttr_mean"] is None

    md = to_markdown(summary)
    assert "| kill | auto | 2 | 2/2 |" in md


def test_fmt():
    assert fmt(None) == "-"
    assert fmt(12.34) == "12.3 s"
    assert fmt(300) == "5.0 min"


def test_first_event():
    events = [
        {"type": "alert_firing", "alertname": "ErrorBudgetBurnFast", "ts": 1},
        {"type": "alert_firing", "alertname": "DemoUnresponsive", "ts": 2},
        {"type": "alert_firing", "alertname": "DemoUnresponsive", "ts": 3},
    ]
    assert first_event(events, "alert_firing", ["DemoUnresponsive"])["ts"] == 2
    assert first_event(events, "action_done", ["DemoUnresponsive"]) is None
