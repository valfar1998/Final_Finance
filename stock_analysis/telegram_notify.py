#!/usr/bin/env python3
"""Alert Telegram quando lo score di un ticker cambia significativamente."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
SIBLING_ENVS = (
    ROOT.parent / "finance-alert" / ".env",
    ROOT.parent / "Finance-Analyzer-main" / ".env",
)

DEFAULT_MIN_DELTA = 3.0


def _parse_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_credentials() -> dict[str, str] | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if token and chat:
        return {"token": token.strip(), "chat_id": chat.strip()}
    for path in (ENV_FILE, *SIBLING_ENVS):
        data = _parse_env(path)
        token = data.get("TELEGRAM_BOT_TOKEN", "")
        chat = data.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
            os.environ.setdefault("TELEGRAM_BOT_TOKEN", token)
            os.environ.setdefault("TELEGRAM_CHAT_ID", chat)
            return {"token": token.strip(), "chat_id": chat.strip()}
    return None


def send_message(text: str) -> bool:
    creds = load_credentials()
    if not creds:
        return False
    url = f"https://api.telegram.org/bot{creds['token']}/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": creds["chat_id"], "text": text[:4000], "disable_web_page_preview": "true"}
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=payload), timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("ok"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return False


def format_score_alert(
    ticker: str,
    *,
    old_score: float | None,
    new_score: float,
    verdict: str,
    buy_target: float | None,
    delta: float,
) -> str:
    arrow = "📈" if delta > 0 else "📉"
    old_bit = f"{old_score:.0f}" if old_score is not None else "N/D"
    lines = [
        f"{arrow} STOCK ANALYSIS — {ticker}",
        f"Score: {old_bit} → {new_score:.0f}/100 ({delta:+.1f})",
        f"Verdetto: {verdict}",
    ]
    if buy_target:
        lines.append(f"🎯 Buy target: ${buy_target:.2f}")
    lines.append(f"https://finance.yahoo.com/quote/{ticker}")
    return "\n".join(lines)


def maybe_notify(
    ticker: str,
    *,
    old_score: float | None,
    new_score: float,
    verdict: str,
    buy_target: float | None,
    min_delta: float | None = None,
) -> bool:
    threshold = min_delta if min_delta is not None else float(
        os.getenv("SCORE_ALERT_MIN_DELTA") or DEFAULT_MIN_DELTA
    )
    if old_score is None:
        return send_message(
            format_score_alert(
                ticker,
                old_score=None,
                new_score=new_score,
                verdict=verdict,
                buy_target=buy_target,
                delta=new_score,
            )
        )
    delta = new_score - old_score
    if abs(delta) < threshold:
        return False
    return send_message(
        format_score_alert(
            ticker,
            old_score=old_score,
            new_score=new_score,
            verdict=verdict,
            buy_target=buy_target,
            delta=delta,
        )
    )
