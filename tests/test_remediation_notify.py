from remediation.notify import Notifier, format_alert


def test_format_alert_firing():
    text = format_alert(
        {
            "status": "firing",
            "labels": {"alertname": "ErrorBudgetBurnFast", "site": "kuponradar", "slo": "latency"},
            "annotations": {"summary": "too slow <b>"},
        }
    )
    assert "🔴" in text and "FIRING" in text
    assert "kuponradar" in text
    assert "var-site=kuponradar" in text
    assert "&lt;b&gt;" in text  # escaped, telegram html would break otherwise


def test_disabled_without_token(capsys):
    n = Notifier(token="", chat_id="")
    assert not n.enabled
    n.send("hello")
    assert "telegram disabled" in capsys.readouterr().out
