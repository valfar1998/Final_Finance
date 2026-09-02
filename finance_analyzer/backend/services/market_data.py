"""Aggregate market data with automatic primary API routing."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import yfinance as yf

from services.data_sources import (
    analyst_chain_for,
    fetch_price_from_provider,
    price_chain_for,
)
from services.analyst_consensus import from_yfinance_mean
from services.fmp import fetch_fmp_analysts, fetch_fmp_history, fetch_fmp_profile_name
from services.stooq import fetch_stooq_history, load_cached_only
from services.twelvedata import fetch_twelvedata_history
from services.yahoo import fetch_yahoo_analysts, fetch_yahoo_chart, fetch_yahoo_name

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY")
FMP_KEY = os.environ.get("FMP_API_KEY")
TWELVE_KEY = os.environ.get("TWELVE_DATA_API_KEY")


def _fetch_finnhub_series(yf_ticker: str) -> pd.Series | None:
    from services.recent_bars import fetch_finnhub_daily
    return fetch_finnhub_daily(yf_ticker, days=3650)


def _fetch_yfinance_series(yf_ticker: str) -> pd.Series:
    t = yf.Ticker(yf_ticker)
    hist = t.history(period="10y", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"yfinance vuoto per {yf_ticker}")
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    return hist["Close"].astype(float)


def resolve_display_name(symbol: str, yf_ticker: str) -> str:
    if FMP_KEY:
        name = fetch_fmp_profile_name(yf_ticker)
        if name:
            return name
    name = fetch_yahoo_name(yf_ticker)
    if name:
        return name
    return symbol


def get_close_prices(stooq_symbol: str, yf_ticker: str) -> tuple[pd.Series, str]:
    """
    Stooq cache/HTTP first, then auto-routed API chain (USA vs internazionale).
    """
    cached = load_cached_only(stooq_symbol)
    if cached is not None:
        return cached.set_index("Date")["Close"].astype(float), "stooq_csv"

    try:
        df = fetch_stooq_history(stooq_symbol)
        return df.set_index("Date")["Close"].astype(float), "stooq"
    except Exception:
        pass

    for provider in price_chain_for(yf_ticker):
        result = fetch_price_from_provider(
            provider,
            yf_ticker,
            fetch_twelve=fetch_twelvedata_history,
            fetch_fmp=fetch_fmp_history,
            fetch_finnhub=_fetch_finnhub_series,
            fetch_yahoo=fetch_yahoo_chart,
            fetch_yfinance=_fetch_yfinance_series,
        )
        if result:
            return result

    raise ValueError(
        f"Impossibile recuperare prezzi per {stooq_symbol} / {yf_ticker}"
    )


def _analyst_from_provider(
    provider: str, yf_ticker: str, current_price: float | None
) -> dict[str, Any] | None:
    if provider == "fmp":
        a = fetch_fmp_analysts(yf_ticker, current_price=current_price)
        if a and a.get("buyability_pct") is not None:
            return a
    elif provider == "yahoo":
        a = fetch_yahoo_analysts(yf_ticker, current_price=current_price)
        if a.get("buyability_pct") is not None:
            return a
    elif provider == "finnhub" and FINNHUB_KEY:
        a = fetch_finnhub_recommendation(yf_ticker, FINNHUB_KEY)
        if a and a.get("buyability_pct") is not None:
            return a
    elif provider == "yfinance":
        try:
            ticker = yf.Ticker(yf_ticker)
            info = ticker.info or {}
            mean = info.get("recommendationMean")
            count = info.get("numberOfAnalystOpinions") or 0
            if mean is not None and mean > 0:
                return from_yfinance_mean(float(mean), int(count))
        except Exception:
            pass
    return None


def get_analyst_buyability(
    yf_ticker: str, asset_type: str, current_price: float | None = None
) -> dict[str, Any]:
    """Analyst buyability with auto-routed primary API (FMP USA, Yahoo intl)."""
    if asset_type == "etf":
        return {
            "buyability_pct": None,
            "recommendation_label": "N/D (ETF)",
            "analyst_count": 0,
            "analyst_target_mean": None,
            "analyst_target_low": None,
            "analyst_target_high": None,
            "analyst_upside_pct": None,
            "market_cap": None,
            "source": "n/a",
        }

    for provider in analyst_chain_for(yf_ticker):
        analyst = _analyst_from_provider(provider, yf_ticker, current_price)
        if analyst:
            return analyst

    return {
        "buyability_pct": None,
        "recommendation_label": "Nessun dato analisti",
        "analyst_count": 0,
        "analyst_target_mean": None,
        "analyst_target_low": None,
        "analyst_target_high": None,
        "analyst_upside_pct": None,
        "source": "none",
    }


def fetch_finnhub_recommendation(symbol: str, api_key: str | None) -> dict[str, Any] | None:
    if not api_key:
        return None
    url = f"https://finnhub.io/api/v1/stock/recommendation?symbol={symbol}&token={api_key}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return None
        latest = data[0]
        buy = latest.get("buy", 0) + latest.get("strongBuy", 0)
        hold = latest.get("hold", 0)
        sell = latest.get("sell", 0) + latest.get("strongSell", 0)
        total = buy + hold + sell
        if total == 0:
            return None
        period = latest.get("period")
        if isinstance(period, str) and len(period) >= 10:
            consensus_date = period[:10]
        else:
            consensus_date = None
        result = {
            "buyability_pct": round((buy / total) * 100, 1),
            "recommendation_label": (
                f"{buy} Buy · {hold} Hold · {sell} Sell su {total} analisti"
            ),
            "analyst_count": total,
            "analyst_buy_count": buy,
            "analyst_hold_count": hold,
            "analyst_sell_count": sell,
            "analyst_consensus_date": consensus_date,
            "source": "finnhub",
        }
        from services.analyst_dates import merge_analyst_dates
        return merge_analyst_dates(result)
    except Exception:
        return None
