from __future__ import annotations

import time
from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import Quote, parse_num

BASE = "https://api.twelvedata.com"


def available() -> bool:
    return bool(env_key("TWELVE_DATA_API_KEY"))


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not available() or not tickers:
        return {}
    out: dict[str, Quote] = {}
    for i, ticker in enumerate(tickers):
        symbol = ticker.split(".")[0].upper()
        try:
            data = get_json(
                f"{BASE}/quote",
                params={"symbol": symbol, "apikey": env_key("TWELVE_DATA_API_KEY")},
            )
        except (HttpError, OSError, TimeoutError, ValueError):
            data = None
        if isinstance(data, dict) and data.get("status") != "error":
            price = parse_num(data.get("close") or data.get("price"))
            prev = parse_num(data.get("previous_close"))
            pct = parse_num(data.get("percent_change"))
            if price is not None:
                out[ticker] = Quote(
                    ticker=ticker,
                    price=price,
                    previous_close=prev,
                    change_pct=pct,
                    source="twelve_data",
                )
        if i + 1 < len(tickers):
            time.sleep(0.15)
    return out
