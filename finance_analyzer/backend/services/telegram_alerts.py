"""Telegram alerts for Finance Analyzer score / buyability changes."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_MIN_DELTA = 5.0


def _load_env_file(path: Path) -> dict[str, str]:
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
    backend = Path(__file__).resolve().parent.parent
    for candidate in (backend.parent / ".env", backend / ".env", backend.parent.parent / "finance-alert" / ".env"):
        data = _load_env_file(candidate)
        token = data.get("TELEGRAM_BOT_TOKEN", "")
        chat = data.get("TELEGRAM_CHAT_ID", "")
        if token and chat:
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


def format_buyability_alert(
    ticker: str,
    *,
    name: str,
    old_buy: float | None,
    new_buy: float,
    price: float | None,
    forecast_pct: float | None,
    delta: float,
) -> str:
    arrow = "📈" if delta > 0 else "📉"
    old_bit = f"{old_buy:.0f}%" if old_buy is not None else "N/D"
    lines = [
        f"{arrow} FINANCE ANALYZER — {name} ({ticker})",
        f"Buyability: {old_bit} → {new_buy:.0f}% ({delta:+.1f} pp)",
    ]
    if price:
        lines.append(f"Prezzo: ${price:.2f}")
    if forecast_pct is not None:
        lines.append(f"Previsione MC: {forecast_pct:+.1f}%")
    lines.append(f"https://finance.yahoo.com/quote/{ticker}")
    return "\n".join(lines)


def maybe_notify_buyability_change(
    ticker: str,
    *,
    name: str,
    old_buy: float | None,
    new_buy: float | None,
    price: float | None,
    forecast_pct: float | None,
    min_delta: float | None = None,
) -> bool:
    if new_buy is None:
        return False
    threshold = min_delta if min_delta is not None else float(
        os.getenv("FA_SCORE_ALERT_MIN_DELTA") or DEFAULT_MIN_DELTA
    )
    if old_buy is None:
        return send_message(
            format_buyability_alert(
                ticker,
                name=name,
                old_buy=None,
                new_buy=new_buy,
                price=price,
                forecast_pct=forecast_pct,
                delta=new_buy,
            )
        )
    delta = new_buy - old_buy
    if abs(delta) < threshold:
        return False
    return send_message(
        format_buyability_alert(
            ticker,
            name=name,
            old_buy=old_buy,
            new_buy=new_buy,
            price=price,
            forecast_pct=forecast_pct,
            delta=delta,
        )
    )
