"""Finds your Telegram chat id and writes it to deploy/.env, then sends a test message.

1. create a bot with @BotFather, put the token into deploy/.env (TELEGRAM_BOT_TOKEN=...)
2. open your bot in Telegram and send it any message (e.g. /start)
3. python -m remediation.telegram_setup
"""

import re
import sys
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).parent.parent / "deploy" / ".env"


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def set_env_value(path: Path, key: str, value: str) -> None:
    text = path.read_text()
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    else:
        text += f"\n{key}={value}\n"
    path.write_text(text)


def find_chat_ids(updates: dict) -> dict[str, str]:
    """chat id -> name, from a getUpdates response"""
    chats = {}
    for update in updates.get("result", []):
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            name = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
            chats[str(chat["id"])] = name
    return chats


def main() -> None:
    env = read_env(ENV_FILE)
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit(f"put TELEGRAM_BOT_TOKEN into {ENV_FILE} first")

    api = f"https://api.telegram.org/bot{token}"
    me = httpx.get(f"{api}/getMe", timeout=10).json()
    if not me.get("ok"):
        sys.exit(f"token doesn't work: {me.get('description')}")
    print(f"bot: @{me['result']['username']}")

    chats = find_chat_ids(httpx.get(f"{api}/getUpdates", timeout=10).json())
    if not chats:
        sys.exit(
            f"no messages yet - open @{me['result']['username']} in Telegram, "
            "send it /start and run this again"
        )
    if len(chats) > 1:
        print("more than one chat found, using the first one:", chats)

    chat_id, name = next(iter(chats.items()))
    set_env_value(ENV_FILE, "TELEGRAM_CHAT_ID", chat_id)
    print(f"chat: {name} -> saved TELEGRAM_CHAT_ID to {ENV_FILE}")

    resp = httpx.post(
        f"{api}/sendMessage",
        json={"chat_id": chat_id, "text": "✅ sitewatch is connected, alerts will come here"},
        timeout=10,
    )
    print("test message sent" if resp.json().get("ok") else f"sending failed: {resp.text}")
    print("now restart the remediator: cd deploy && docker compose up -d remediator")


if __name__ == "__main__":
    main()
