"""Twelve Data API (free tier: 800 req/day, US + some global)."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd

TWELVE_BASE = "https://api.twelvedata.com"

# Yahoo/Finnhub suffix -> Twelve Data exchange code
EXCHANGE_MAP = {
    ".MI": "MTA",   # Milano
    ".DE": "XETR",  # XETRA
    ".L": "LSE",
    ".PA": "EPA",   # Paris
    ".AS": "AMS",
    ".MC": "BME",
    ".SW": "SIX",
    ".T": "TSE",
    ".HK": "HKEX",
    ".TO": "TSX",
    ".KS": "KRX",
    ".TW": "TWSE",
    ".SS": "SSE",
    ".SZ": "SZSE",
    ".SI": "SGX",
}


def _key() -> str | None:
    return os.environ.get("TWELVE_DATA_API_KEY")


def _to_twelve_symbol(ticker: str) -> str:
    """Convert AAPL or ENEL.MI -> Twelve Data symbol format."""
    if ":" in ticker:
        return ticker
    upper = ticker.upper()
    for suffix, exchange in EXCHANGE_MAP.items():
        if upper.endswith(suffix):
            base = upper[: -len(suffix)]
            return f"{base}:{exchange}"
    return upper.split(".")[0]


def fetch_twelvedata_history(ticker: str, outputsize: int = 5000) -> pd.Series | None:
    api_key = _key()
    if not api_key:
        return None

    symbol = _to_twelve_symbol(ticker)
    url = f"{TWELVE_BASE}/time_series"
    params = {
        "symbol": symbol,
        "interval": "1day",
        "outputsize": outputsize,
        "apikey": api_key,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "error" or "values" not in data:
                if ":" in symbol:
                    params["symbol"] = ticker.split(".")[0].upper()
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                if data.get("status") == "error" or "values" not in data:
                    return None

        values = data["values"]
        rows = []
        for row in values:
            d = row.get("datetime", "")[:10]
            c = row.get("close")
            if d and c is not None:
                rows.append((pd.Timestamp(d), float(c)))
        if not rows:
            return None
        series = pd.Series({d: v for d, v in rows}).sort_index()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        return series.astype(float)
    except Exception:
        return None


def fetch_twelvedata_quote(ticker: str) -> dict[str, Any] | None:
    """Single latest quote (1 API credit)."""
    api_key = _key()
    if not api_key:
        return None
    symbol = _to_twelve_symbol(ticker)
    url = f"{TWELVE_BASE}/quote"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"symbol": symbol, "apikey": api_key})
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") == "error":
            return None
        return data
    except Exception:
        return None
