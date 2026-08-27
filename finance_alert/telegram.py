"""Stesso bot Telegram di calcio/recensioni: TELEGRAM_BOT_TOKEN + CHAT_ID."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from finance_alert.env import ROOT, SIBLING_ENV_DIRS, clean_secret, parse_env_file


def _bot_probe(token: str) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("ok"):
            username = (body.get("result") or {}).get("username") or "?"
            return True, f"ok (@{username})"
        return False, str(body.get("description") or body)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        return False, f"HTTP {exc.code} {detail}".strip()
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
        return False, str(exc)


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
    # In GitHub Actions i secret arrivano solo da env: non cercare .env locali.
    if os.getenv("GITHUB_ACTIONS") == "true":
        return found
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


def diagnose_telegram() -> str:
    raw_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    raw_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    token = clean_secret(raw_token)
    chat = clean_secret(raw_chat)
    bits = [
        f"token_present={bool(token)}",
        f"token_len={len(token)}",
        f"chat_present={bool(chat)}",
        f"chat_len={len(chat)}",
        f"candidates={len(_candidates())}",
    ]
    if token:
        ok, detail = _bot_probe(token)
        bits.append(f"getMe={ok} ({detail})")
    return "telegram diag: " + ", ".join(bits)


def load_credentials() -> dict[str, str] | None:
    candidates = _candidates()
    if not candidates:
        print(diagnose_telegram())
        print(
            "telegram skip: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID assenti o vuoti "
            "(su GitHub: Settings → Secrets → Actions, poi Update secret con il valore)."
        )
        return None
    last_err = ""
    for token, chat, source in candidates:
        ok, detail = _bot_probe(token)
        if not ok:
            last_err = detail
            continue
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        os.environ["TELEGRAM_CHAT_ID"] = chat
        return {"token": token, "chat_id": chat, "source": source}
    print(diagnose_telegram())
    print(f"telegram skip: token presente ma getMe fallito ({last_err})")
    return None


def send_message(text: str) -> bool:
    creds = load_credentials()
    if not creds:
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
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        print(f"telegram errore: HTTP {exc.code} {detail}".strip())
        return False
    except urllib.error.URLError as exc:
        print(f"telegram errore: {exc}")
        return False
