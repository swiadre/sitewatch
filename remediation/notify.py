"""Telegram notifications. Without TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID it only prints."""

import html
import os

import httpx

GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")


def dashboard_link(site: str | None) -> str:
    url = f"{GRAFANA_URL}/d/sitewatch-overview/sitewatch-overview"
    if site:
        url += f"?var-site={site}"
    return url


def format_alert(alert: dict) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    firing = alert.get("status") == "firing"
    icon = "🔴" if firing else "✅"
    status = "FIRING" if firing else "RESOLVED"
    site = labels.get("site")

    lines = [f"{icon} <b>{status}: {html.escape(labels.get('alertname', '?'))}</b>"]
    if site:
        slo = f" ({labels['slo']})" if "slo" in labels else ""
        lines.append(f"site: <b>{html.escape(site)}</b>{html.escape(slo)}")
    if labels.get("severity"):
        lines.append(f"severity: {html.escape(labels['severity'])}")
    if annotations.get("summary"):
        lines.append(html.escape(annotations["summary"]))
    if annotations.get("description"):
        lines.append(f"<i>{html.escape(annotations['description'])}</i>")
    lines.append(f'<a href="{dashboard_link(site)}">dashboard</a>')
    return "\n".join(lines)


class Notifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID")

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            print(f"[telegram disabled] {text}", flush=True)
            return
        try:
            resp = httpx.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[telegram] error {resp.status_code}: {resp.text[:200]}", flush=True)
        except httpx.HTTPError as e:
            # alerting must never crash the remediator
            print(f"[telegram] failed: {e!r}", flush=True)
