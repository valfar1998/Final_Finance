"""Persistenza stato alert: Upstash Redis (REST) con fallback su file locale."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from finance_alert.env import ROOT

SENT_KEY = "finance-alert:telegram_alerts_sent"
LOCAL_SENT = ROOT / "data" / "telegram_alerts_sent.json"


def _upstash_creds() -> tuple[str, str] | None:
    url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.getenv("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if url and token:
        return url, token
    return None


def redis_available() -> bool:
    return _upstash_creds() is not None


def _redis_command(*args: str) -> Any | None:
    creds = _upstash_creds()
    if not creds:
        return None
    url, token = creds
    payload = json.dumps(list(args)).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if isinstance(body, dict) and body.get("error"):
        return None
    return body.get("result") if isinstance(body, dict) else body


def load_sent_raw() -> dict | list | None:
    if redis_available():
        raw = _redis_command("GET", SENT_KEY)
        if raw:
            try:
                return json.loads(str(raw))
            except json.JSONDecodeError:
                pass
    if LOCAL_SENT.is_file():
        try:
            return json.loads(LOCAL_SENT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
    return None


def save_sent_raw(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if redis_available():
        _redis_command("SET", SENT_KEY, text)
    LOCAL_SENT.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_SENT.write_text(text, encoding="utf-8")
