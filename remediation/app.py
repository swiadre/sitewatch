"""Remediator: gets alerts from Alertmanager (webhook), notifies Telegram,
and for known problems fixes them automatically.

POST /alerts   <- alertmanager webhook
POST /deploy   {"version": "1.1"}           deploy a version of the demo app
POST /auto     {"enabled": false}           turn auto-remediation on/off (for chaos tests)
GET  /events?since=<unix ts>                event log (for MTTD / MTTR)
GET  /metrics
"""

import os
import threading
import time

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

from remediation.events import EventLog
from remediation.notify import Notifier, format_alert
from remediation.policy import RateLimiter, pick_action

DATA_DIR = os.environ.get("DATA_DIR", "/data")

ACTIONS_TOTAL = Counter(
    "remediation_actions_total", "Auto-remediation actions", ["action", "result"]
)
ACTION_DURATION = Histogram(
    "remediation_action_duration_seconds", "How long an action took", ["action"]
)
LAST_DEPLOY = Gauge("demo_last_deploy_timestamp_seconds", "Unix time of the last demo app deploy")
AUTO_ENABLED = Gauge("remediation_auto_enabled", "1 if auto-remediation is on")


class DeployRequest(BaseModel):
    version: str


class AutoRequest(BaseModel):
    enabled: bool


def create_app(demo=None, notifier=None, limiter=None, events=None) -> FastAPI:
    """demo/notifier/limiter/events can be swapped with fakes in tests."""
    if demo is None:
        from remediation.docker_ops import DemoApp

        demo = DemoApp(state_file=f"{DATA_DIR}/deployments.json")
    notifier = notifier or Notifier()
    limiter = limiter or RateLimiter(
        max_actions=int(os.environ.get("MAX_ACTIONS_PER_HOUR", "3")),
        cooldown_seconds=float(os.environ.get("ACTION_COOLDOWN_SECONDS", "120")),
    )
    events = events or EventLog(f"{DATA_DIR}/events.jsonl")
    state = {"auto": os.environ.get("AUTO_REMEDIATION", "true").lower() == "true"}
    action_lock = threading.Lock()  # one action at a time

    AUTO_ENABLED.set(1 if state["auto"] else 0)
    if demo.last_deploy_time():
        LAST_DEPLOY.set(demo.last_deploy_time())

    app = FastAPI(title="sitewatch remediator")

    def run_action(action: str, alert: dict) -> None:
        labels = alert.get("labels", {})
        target = labels.get("site", "?")
        name = labels.get("alertname")

        if not state["auto"]:
            events.add("action_skipped", action=action, alertname=name, reason="auto disabled")
            return

        with action_lock:
            verdict = limiter.check(action, target)
            if not verdict.allowed:
                events.add("action_skipped", action=action, alertname=name, reason=verdict.reason)
                ACTIONS_TOTAL.labels(action, "skipped").inc()
                notifier.send(
                    f"⚠️ <b>auto-remediation NOT done</b> for {name} ({target}): "
                    f"{verdict.reason}\nA human needs to look at this!"
                )
                return

            limiter.record(action, target)
            events.add("action_started", action=action, alertname=name, site=target)
            start = time.time()
            try:
                result = getattr(demo, action)()
            except Exception as e:  # anything from docker
                ACTIONS_TOTAL.labels(action, "error").inc()
                events.add("action_failed", action=action, alertname=name, error=repr(e))
                notifier.send(f"❌ auto-remediation <b>{action}</b> failed: {e!r}")
                return

            took = time.time() - start
            ACTIONS_TOTAL.labels(action, "ok").inc()
            ACTION_DURATION.labels(action).observe(took)
            if action == "rollback" and demo.last_deploy_time():
                LAST_DEPLOY.set(demo.last_deploy_time())
            events.add(
                "action_done",
                action=action,
                alertname=name,
                site=target,
                duration_s=round(took, 2),
                result=result,
            )
            notifier.send(f"🔧 auto-remediation: <b>{action}</b> on {target} done in {took:.1f}s")

    @app.post("/alerts")
    def alerts(payload: dict):
        for alert in payload.get("alerts", []):
            labels = alert.get("labels", {})
            events.add(
                f"alert_{alert.get('status')}",
                alertname=labels.get("alertname"),
                site=labels.get("site"),
                starts_at=alert.get("startsAt"),
            )
            notifier.send(format_alert(alert))

            action = pick_action(alert)
            if action and alert.get("status") == "firing":
                # don't block the webhook, alertmanager has a timeout
                threading.Thread(target=run_action, args=(action, alert), daemon=True).start()
        return {"ok": True}

    @app.post("/deploy")
    def deploy(req: DeployRequest):
        with action_lock:
            entry = demo.deploy(req.version, reason="manual")
        LAST_DEPLOY.set(entry["ts"])
        events.add("deploy", version=req.version)
        notifier.send(f"🚀 deployed demo app version <b>{req.version}</b>")
        return entry

    @app.post("/auto")
    def auto(req: AutoRequest):
        state["auto"] = req.enabled
        AUTO_ENABLED.set(1 if req.enabled else 0)
        events.add("auto_toggled", enabled=req.enabled)
        return {"auto": state["auto"]}

    @app.get("/events")
    def get_events(since: float = 0):
        return events.since(since)

    @app.get("/status")
    def status():
        return {
            "auto": state["auto"],
            "version": demo.current_version(),
            "history": demo.history()[-5:],
        }

    @app.get("/metrics")
    def metrics():
        return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def main() -> None:
    import uvicorn

    from remediation.docker_ops import DemoApp

    demo = DemoApp(state_file=f"{DATA_DIR}/deployments.json")
    demo.ensure_running(default_version=os.environ.get("DEMO_DEFAULT_VERSION", "1.0"))
    uvicorn.run(create_app(demo=demo), host="0.0.0.0", port=9000)


if __name__ == "__main__":
    main()
