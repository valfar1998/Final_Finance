"""Fetch recent price bars (Stooq cache → Finnhub → Yahoo)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import pandas as pd

from services.market_data import get_close_prices

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY")


def fetch_finnhub_daily(yf_ticker: str, days: int = 30) -> pd.Series | None:
    if not FINNHUB_KEY:
        return None
    now = int(time.time())
    start = now - days * 86400 * 2  # buffer weekends
    url = (
        f"https://finnhub.io/api/v1/stock/candle?"
        f"symbol={yf_ticker}&resolution=D&from={start}&to={now}&token={FINNHUB_KEY}"
    )
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        if data.get("s") != "ok" or not data.get("c"):
            return None
        rows = [
            (pd.Timestamp(t, unit="s"), float(c))
            for t, c in zip(data["t"], data["c"])
            if c is not None
        ]
        if not rows:
            return None
        series = pd.Series({d: v for d, v in rows}).sort_index()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        return series.astype(float)
    except Exception:
        return None


def get_recent_bars(
    stooq_symbol: str,
    yf_ticker: str,
    days: int = 20,
) -> dict[str, Any]:
    """Last N trading days for detail sparkline."""
    source = "unknown"
    prices: pd.Series | None = None

    # 1) Stooq / Yahoo via existing pipeline
    try:
        prices, source = get_close_prices(stooq_symbol, yf_ticker)
    except Exception:
        prices = None

    # 2) Finnhub fallback
    if prices is None or prices.empty:
        fh = fetch_finnhub_daily(yf_ticker, days=days + 10)
        if fh is not None and not fh.empty:
            prices = fh
            source = "finnhub"

    if prices is None or prices.empty:
        raise ValueError(f"Nessun dato recente per {yf_ticker}")

    tail = prices.dropna().tail(days)
    bars = [
        {"date": d.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
        for d, v in tail.items()
    ]
    return {
        "bars": bars,
        "source": source,
        "count": len(bars),
        "from_date": bars[0]["date"] if bars else None,
        "to_date": bars[-1]["date"] if bars else None,
    }
