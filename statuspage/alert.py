"""Telegram alert from the GitHub Actions prober (works when my laptop is off).

Run after every probe. Looks at the history in the data branch and sends a message only
when a site changes state:
- DOWN:      the last 2 probes failed and the one before was OK (2 probes = ~10 min,
             so one random timeout doesn't wake anybody up)
- RECOVERED: the last probe is OK and the 2 before it failed (= we sent a DOWN before)

    python -m statuspage.alert --data data-branch/data
"""

import argparse
import os
from pathlib import Path

import httpx

from statuspage.stats import load_rows

CONSECUTIVE = 2
STATUS_PAGE = "https://swiadre.github.io/sitewatch/"


def state_change(rows: list[dict], n: int = CONSECUTIVE) -> str | None:
    """rows = one site's probes, oldest first. Returns "down", "recovered" or None."""
    known = [r["up"] for r in rows if r["up"] is not None]
    if len(known) < n + 1:
        return None
    last, before = known[-n:], known[-(n + 1)]
    if not any(last) and before:
        return "down"
    if known[-1] and not any(known[-(n + 1) : -1]):
        return "recovered"
    return None


def message(site: str, change: str, rows: list[dict]) -> str:
    last = rows[-1]
    if change == "down":
        error = last.get("error") or f"HTTP {last.get('status')}"
        return (
            f"🔴 <b>{site} is DOWN</b> (seen from GitHub Actions)\n"
            f"failed {CONSECUTIVE} probes in a row, last error: <code>{error}</code>\n"
            f'<a href="{STATUS_PAGE}">status page</a>'
        )
    return f"✅ <b>{site} recovered</b> (seen from GitHub Actions)"


def send(text: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id):
        print(f"[telegram not configured] {text}")
        return
    resp = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=10,
    )
    print("sent" if resp.status_code == 200 else f"telegram error {resp.status_code}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data")
    parser.add_argument("--test", action="store_true", help="just send a test message")
    args = parser.parse_args()

    if args.test:
        send(f'🧪 test alert from GitHub Actions. <a href="{STATUS_PAGE}">status page</a>')
        return

    rows = load_rows(Path(args.data))
    for site in sorted({r["site"] for r in rows}):
        site_rows = [r for r in rows if r["site"] == site]
        change = state_change(site_rows)
        if change:
            send(message(site, change, site_rows))


if __name__ == "__main__":
    main()
