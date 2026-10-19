import time

from fastapi.testclient import TestClient

from remediation.app import create_app
from remediation.events import EventLog
from remediation.policy import RateLimiter


class FakeDemo:
    def __init__(self):
        self.calls = []
        self.versions = ["1.0"]

    def current_version(self):
        return self.versions[-1]

    def last_deploy_time(self):
        return 123.0

    def history(self):
        return [{"version": v} for v in self.versions]

    def restart(self):
        self.calls.append("restart")
        return {}

    def rollback(self):
        self.calls.append("rollback")
        self.versions.append(self.versions[-2])
        return {}

    def cleanup_disk(self):
        self.calls.append("cleanup_disk")
        return {}

    def deploy(self, version, reason=""):
        self.versions.append(version)
        return {"version": version, "ts": time.time()}


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, text):
        self.messages.append(text)


def alert(name="DemoUnresponsive", status="firing", remediation="restart"):
    labels = {"alertname": name, "site": "demo", "severity": "page"}
    if remediation:
        labels["remediation"] = remediation
    return {"status": status, "labels": labels, "annotations": {"summary": "demo is down"}}


def make(tmp_path, max_actions=3):
    demo, notifier = FakeDemo(), FakeNotifier()
    events = EventLog(tmp_path / "events.jsonl")
    app = create_app(
        demo=demo,
        notifier=notifier,
        limiter=RateLimiter(max_actions=max_actions, cooldown_seconds=0),
        events=events,
    )
    return TestClient(app), demo, notifier, events


def wait_for(cond, timeout=2):
    # actions run in a background thread
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_firing_alert_triggers_restart(tmp_path):
    client, demo, notifier, events = make(tmp_path)
    resp = client.post("/alerts", json={"alerts": [alert()]})
    assert resp.status_code == 200
    assert wait_for(lambda: demo.calls == ["restart"])
    assert wait_for(lambda: any(e["type"] == "action_done" for e in events.since()))
    assert any("FIRING" in m for m in notifier.messages)


def test_resolved_alert_does_nothing(tmp_path):
    client, demo, notifier, events = make(tmp_path)
    client.post("/alerts", json={"alerts": [alert(status="resolved")]})
    time.sleep(0.1)
    assert demo.calls == []
    assert any("RESOLVED" in m for m in notifier.messages)


def test_alert_without_remediation_only_notifies(tmp_path):
    client, demo, notifier, _ = make(tmp_path)
    client.post("/alerts", json={"alerts": [alert(name="ErrorBudgetBurnFast", remediation=None)]})
    time.sleep(0.1)
    assert demo.calls == []
    assert len(notifier.messages) == 1


def test_auto_disabled(tmp_path):
    client, demo, _, events = make(tmp_path)
    client.post("/auto", json={"enabled": False})
    client.post("/alerts", json={"alerts": [alert()]})
    assert wait_for(lambda: any(e["type"] == "action_skipped" for e in events.since()))
    assert demo.calls == []


def test_rate_limit_hands_over_to_human(tmp_path):
    client, demo, notifier, _ = make(tmp_path, max_actions=1)
    client.post("/alerts", json={"alerts": [alert()]})
    assert wait_for(lambda: demo.calls == ["restart"])
    client.post("/alerts", json={"alerts": [alert()]})
    assert wait_for(lambda: any("human" in m for m in notifier.messages))
    assert demo.calls == ["restart"]


def test_deploy_and_events(tmp_path):
    client, demo, _, _ = make(tmp_path)
    before = time.time()
    resp = client.post("/deploy", json={"version": "1.1-bad"})
    assert resp.json()["version"] == "1.1-bad"
    evs = client.get("/events", params={"since": before}).json()
    assert [e["type"] for e in evs] == ["deploy"]
    assert client.get("/status").json()["version"] == "1.1-bad"
