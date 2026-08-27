"""Stesso bot Telegram di calcio/recensioni: TELEGRAM_BOT_TOKEN + CHAT_ID."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from finance_alert.env import ROOT, SIBLING_ENV_DIRS, clean_secret, parse_env_file


def _bot_alive(token: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("ok"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return False


def _candidates() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(token: str, chat: str, source: str) -> None:
        token, chat = clean_secret(token), clean_secret(chat)
        key = (token, chat)
        if not token or not chat or key in seen:
            return
        seen.add(key)
        found.append((token, chat, source))

    add(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""), "env")
    local = parse_env_file(ROOT / ".env")
    add(local.get("TELEGRAM_BOT_TOKEN", ""), local.get("TELEGRAM_CHAT_ID", ""), "local")
    parent = ROOT.parent
    for name in SIBLING_ENV_DIRS:
        data = parse_env_file(parent / name / ".env")
        add(
            data.get("TELEGRAM_BOT_TOKEN", ""),
            data.get("TELEGRAM_CHAT_ID", ""),
            name,
        )
    return found


def load_credentials() -> dict[str, str] | None:
    for token, chat, source in _candidates():
        if not _bot_alive(token):
            continue
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        os.environ["TELEGRAM_CHAT_ID"] = chat
        return {"token": token, "chat_id": chat, "source": source}
    return None


def send_message(text: str) -> bool:
    creds = load_credentials()
    if not creds:
        print("telegram skip: manca TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
        return False
    url = f"https://api.telegram.org/bot{creds['token']}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": creds["chat_id"],
            "text": text[:4000],
            "disable_web_page_preview": "true",
        }
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if not body.get("ok"):
            print(f"telegram errore: {body.get('description') or body}")
            return False
        return True
    except urllib.error.URLError as exc:
        print(f"telegram errore: {exc}")
        return False
