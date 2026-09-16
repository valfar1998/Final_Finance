"""Stesso bot Telegram di calcio/recensioni: TELEGRAM_BOT_TOKEN + CHAT_ID."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from finance_alert.env import ROOT, SIBLING_ENV_DIRS, clean_secret, parse_env_file

_PROBE_TIMEOUT = 20
_SEND_TIMEOUT = 25
_MAX_ATTEMPTS = 4
_TRANSIENT_MARKERS = (
    "timed out",
    "timeout",
    "temporarily unavailable",
    "connection reset",
    "connection aborted",
    "broken pipe",
    "name or service not known",
    "temporary failure",
    "network is unreachable",
    "remote end closed",
    "errno 104",
    "errno 110",
)


def _is_transient(detail: str) -> bool:
    d = (detail or "").lower()
    return any(m in d for m in _TRANSIENT_MARKERS)


def _sleep_backoff(attempt: int) -> None:
    # 1.5s, 3s, 6s…
    time.sleep(1.5 * (2**attempt))


def _bot_probe(token: str, *, attempts: int = _MAX_ATTEMPTS) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{token}/getMe"
    last_err = ""
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=_PROBE_TIMEOUT) as resp:
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
            last_err = f"HTTP {exc.code} {detail}".strip()
            # 401/403 = token invalido; 429/5xx = ritenta
            if exc.code in (401, 403, 404):
                return False, last_err
            if attempt + 1 < attempts and (exc.code == 429 or exc.code >= 500):
                _sleep_backoff(attempt)
                continue
            return False, last_err
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
            last_err = str(exc)
            if attempt + 1 < attempts and _is_transient(last_err):
                _sleep_backoff(attempt)
                continue
            return False, last_err
    return False, last_err or "probe failed"


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


def diagnose_telegram(*, getme_detail: str | None = None) -> str:
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
    if getme_detail is not None:
        bits.append(f"getMe={getme_detail}")
    elif token:
        ok, detail = _bot_probe(token, attempts=1)
        bits.append(f"getMe={ok} ({detail})")
    return "telegram diag: " + ", ".join(bits)


def load_credentials() -> dict[str, str] | None:
    candidates = _candidates()
    if not candidates:
        print(diagnose_telegram(getme_detail="skipped"))
        print(
            "telegram skip: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID assenti o vuoti "
            "(su GitHub: Settings → Secrets → Actions, poi Update secret con il valore)."
        )
        return None
    last_err = ""
    transient_fallback: dict[str, str] | None = None
    for token, chat, source in candidates:
        ok, detail = _bot_probe(token)
        if ok:
            os.environ["TELEGRAM_BOT_TOKEN"] = token
            os.environ["TELEGRAM_CHAT_ID"] = chat
            return {"token": token, "chat_id": chat, "source": source}
        last_err = detail
        # Timeout/rete su getMe: non bloccare l'invio — sendMessage ritenta a sua volta.
        if transient_fallback is None and _is_transient(detail):
            transient_fallback = {"token": token, "chat_id": chat, "source": source}
            print(f"telegram warn: getMe transient ({detail}), provo comunque sendMessage")
    if transient_fallback:
        os.environ["TELEGRAM_BOT_TOKEN"] = transient_fallback["token"]
        os.environ["TELEGRAM_CHAT_ID"] = transient_fallback["chat_id"]
        return transient_fallback
    print(diagnose_telegram(getme_detail=f"False ({last_err})"))
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
    last_err = ""
    for attempt in range(_MAX_ATTEMPTS):
        try:
            req = urllib.request.Request(url, data=payload)
            with urllib.request.urlopen(req, timeout=_SEND_TIMEOUT) as resp:
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
            last_err = f"HTTP {exc.code} {detail}".strip()
            if exc.code in (401, 403, 400):
                print(f"telegram errore: {last_err}")
                return False
            if attempt + 1 < _MAX_ATTEMPTS and (exc.code == 429 or exc.code >= 500):
                _sleep_backoff(attempt)
                continue
            print(f"telegram errore: {last_err}")
            return False
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last_err = str(exc)
            if attempt + 1 < _MAX_ATTEMPTS and _is_transient(last_err):
                _sleep_backoff(attempt)
                continue
            print(f"telegram errore: {last_err}")
            return False
    print(f"telegram errore: {last_err}")
    return False
