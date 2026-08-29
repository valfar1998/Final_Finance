from __future__ import annotations

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import Quote, parse_num

BASE = "https://api.twelvedata.com"


def available() -> bool:
    return bool(env_key("TWELVE_DATA_API_KEY"))


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    """Una sola richiesta batch (symbol=AAPL,MSFT,...) quando possibile."""
    if not available() or not tickers:
        return {}
    by_us = {t.split(".")[0].upper(): t for t in tickers}
    symbols = ",".join(by_us.keys())
    try:
        data = get_json(
            f"{BASE}/quote",
            params={"symbol": symbols, "apikey": env_key("TWELVE_DATA_API_KEY")},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return {}

    rows: dict[str, dict] = {}
    if isinstance(data, dict):
        if data.get("status") == "error":
            return {}
        # Singolo ticker → oggetto piatto; multi → mappa symbol → quote
        if "symbol" in data and ("close" in data or "price" in data):
            us = str(data.get("symbol") or "").upper()
            if us:
                rows[us] = data
        else:
            for us, row in data.items():
                if isinstance(row, dict) and row.get("status") != "error":
                    rows[str(us).upper()] = row

    out: dict[str, Quote] = {}
    for us, row in rows.items():
        ticker = by_us.get(us)
        if not ticker:
            continue
        price = parse_num(row.get("close") or row.get("price"))
        if price is None:
            continue
        out[ticker] = Quote(
            ticker=ticker,
            price=price,
            previous_close=parse_num(row.get("previous_close")),
            change_pct=parse_num(row.get("percent_change")),
            source="twelve_data",
        )
    return out
