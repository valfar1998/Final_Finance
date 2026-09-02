"""Yahoo Finance direct API (free, no API key). Chart + analyst recommendations."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
import pandas as pd

from services.analyst_consensus import build_consensus
from services.analyst_dates import (
    dates_from_yahoo_history,
    merge_analyst_dates,
    yahoo_trend_period_to_date,
)

_SESSION: httpx.Client | None = None
_CRUMB: str | None = None
_CRUMB_TS: float = 0.0
_LAST_YAHOO_CALL: float = 0.0
_MIN_YAHOO_INTERVAL = 0.12  # ~8 req/s max per quoteSummary

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _client() -> httpx.Client:
    global _SESSION
    if _SESSION is None:
        _SESSION = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=30.0)
    return _SESSION


def _throttle_yahoo() -> None:
    global _LAST_YAHOO_CALL
    elapsed = time.time() - _LAST_YAHOO_CALL
    if elapsed < _MIN_YAHOO_INTERVAL:
        time.sleep(_MIN_YAHOO_INTERVAL - elapsed)
    _LAST_YAHOO_CALL = time.time()


def _get_crumb() -> str:
    global _CRUMB, _CRUMB_TS
    if _CRUMB and (time.time() - _CRUMB_TS) < 3600:
        return _CRUMB
    client = _client()
    client.get("https://fc.yahoo.com")
    resp = client.get("https://query2.finance.yahoo.com/v1/test/getcrumb")
    resp.raise_for_status()
    _CRUMB = resp.text.strip()
    _CRUMB_TS = time.time()
    return _CRUMB


def fetch_yahoo_chart(ticker: str, range_: str = "10y", interval: str = "1d") -> pd.Series:
    """Daily close prices from Yahoo chart API."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval={interval}&range={range_}"
    )
    resp = _client().get(url)
    resp.raise_for_status()
    payload = resp.json()
    result = payload["chart"]["result"]
    if not result:
        raise ValueError(f"Nessun dato Yahoo chart per '{ticker}'")

    block = result[0]
    timestamps = block.get("timestamp") or []
    quotes = block["indicators"]["quote"][0]
    closes = quotes.get("close") or []

    rows: list[tuple[datetime, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        rows.append((datetime.utcfromtimestamp(ts), float(close)))

    if not rows:
        raise ValueError(f"Serie prezzi vuota per '{ticker}'")

    series = pd.Series({d: v for d, v in rows}).sort_index()
    series.index = pd.to_datetime(series.index).tz_localize(None)
    return series.astype(float)


def _raw_value(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict) and val.get("raw") is not None:
        return float(val["raw"])
    return None


def fetch_yahoo_analysts(ticker: str, current_price: float | None = None) -> dict[str, Any]:
    """
    Buy/Hold/Sell consensus from Yahoo recommendationTrend.
    Target price kept as info (upside) but does not drive buyability_pct.
    """
    result: dict[str, Any] = {
        "buyability_pct": None,
        "recommendation_label": "N/D",
        "analyst_count": 0,
        "analyst_target_mean": None,
        "analyst_target_low": None,
        "analyst_target_high": None,
        "analyst_upside_pct": None,
        "market_cap": None,
        "source": "yahoo",
    }
    try:
        _throttle_yahoo()
        crumb = _get_crumb()
        url = (
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{ticker}?modules=financialData,price,recommendationTrend,summaryDetail,upgradeDowngradeHistory&crumb={crumb}"
        )
        resp = _client().get(url)
        if resp.status_code == 429:
            time.sleep(2.0)
            _throttle_yahoo()
            resp = _client().get(url)
        if resp.status_code != 200:
            return result
        data = resp.json()
        block = data.get("quoteSummary", {}).get("result", [{}])[0]
        financial = block.get("financialData", {})
        price_block = block.get("price", {})
        summary = block.get("summaryDetail", {})
        trends = block.get("recommendationTrend", {}).get("trend", [])
        history = block.get("upgradeDowngradeHistory", {}).get("history", [])
        date_meta = dates_from_yahoo_history(history)
        consensus_date = None
        if trends:
            consensus_date = yahoo_trend_period_to_date(str(trends[0].get("period", "")))

        target_mean = _raw_value(financial.get("targetMeanPrice"))
        target_low = _raw_value(financial.get("targetLowPrice"))
        target_high = _raw_value(financial.get("targetHighPrice"))
        analyst_count = int(_raw_value(financial.get("numberOfAnalystOpinions")) or 0)
        market_cap = _raw_value(price_block.get("marketCap")) or _raw_value(summary.get("marketCap"))

        current = current_price
        if current is None:
            current = _raw_value(price_block.get("regularMarketPrice"))
        if current is None:
            current = _raw_value(financial.get("currentPrice"))

        result["analyst_target_mean"] = target_mean
        result["analyst_target_low"] = target_low
        result["analyst_target_high"] = target_high
        result["analyst_count"] = analyst_count
        result["market_cap"] = market_cap

        # Primary: Buy / Hold / Sell counts (consenso analisti)
        if trends:
            latest = trends[0]
            consensus = build_consensus(
                strong_buy=int(latest.get("strongBuy") or 0),
                buy=int(latest.get("buy") or 0),
                hold=int(latest.get("hold") or 0),
                sell=int(latest.get("sell") or 0),
                strong_sell=int(latest.get("strongSell") or 0),
                source="yahoo",
                target_mean=target_mean,
                target_low=target_low,
                target_high=target_high,
                current_price=current,
            )
            if consensus.get("buyability_pct") is not None:
                consensus["market_cap"] = market_cap
                consensus["analyst_count"] = max(analyst_count, consensus["analyst_count"])
                consensus["analyst_consensus_date"] = consensus_date
                consensus.update(date_meta)
                return merge_analyst_dates(consensus)

        # Solo target price, senza rating buy/hold/sell
        if target_mean is not None:
            consensus = build_consensus(
                source="yahoo",
                target_mean=target_mean,
                target_low=target_low,
                target_high=target_high,
                current_price=current,
            )
            consensus["market_cap"] = market_cap
            consensus["analyst_count"] = analyst_count
            consensus["analyst_consensus_date"] = consensus_date
            consensus.update(date_meta)
            return merge_analyst_dates(consensus)

        return result

    except Exception:
        result["recommendation_label"] = "Errore recupero previsioni analisti"

    return result


def fetch_yahoo_name(ticker: str) -> str | None:
    try:
        crumb = _get_crumb()
        url = (
            "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{ticker}?modules=price&crumb={crumb}"
        )
        resp = _client().get(url)
        if resp.status_code != 200:
            return None
        data = resp.json()
        price = data["quoteSummary"]["result"][0]["price"]
        return price.get("longName") or price.get("shortName")
    except Exception:
        return None
