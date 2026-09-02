"""Automatic primary API selection (no manual tuning required)."""

from __future__ import annotations

import os
from typing import Callable, Literal

import pandas as pd

PriceProvider = Literal["twelve_data", "fmp", "finnhub", "yahoo_chart", "yfinance"]
AnalystProvider = Literal["fmp", "yahoo", "finnhub", "yfinance"]

# Exchange suffixes on Yahoo/Finnhub tickers → international (non-US primary path)
INTL_SUFFIXES = (
    ".MI", ".DE", ".L", ".PA", ".AS", ".MC", ".SW", ".T", ".HK",
    ".TO", ".KS", ".TW", ".SS", ".SZ", ".SI", ".AX", ".OL", ".HE",
    ".ST", ".CO", ".BR", ".VI", ".PR", ".WA", ".SA", ".MX",
)

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY")
FMP_KEY = os.environ.get("FMP_API_KEY")
TWELVE_KEY = os.environ.get("TWELVE_DATA_API_KEY")


def is_us_ticker(yf_ticker: str) -> bool:
    upper = yf_ticker.upper()
    return not any(upper.endswith(s) for s in INTL_SUFFIXES)


def _configured(*keys: str | None) -> bool:
    return any(k for k in keys)


def price_chain_for(yf_ticker: str) -> list[PriceProvider]:
    """
    Auto routing:
    - USA: Twelve Data (800/giorno) → FMP → Finnhub → Yahoo
    - Internazionale: Finnhub → Yahoo → Twelve Data → yfinance
    Stooq cache/HTTP is always tried before this chain in market_data.
    """
    override = (os.environ.get("PRIMARY_PRICE_API") or "auto").strip().lower()
    if override not in ("", "auto"):
        chain: list[PriceProvider] = []
        for name in override.split(","):
            n = name.strip()
            if n in ("twelve_data", "fmp", "finnhub", "yahoo_chart", "yfinance"):
                chain.append(n)  # type: ignore[arg-type]
        if chain:
            return chain

    if is_us_ticker(yf_ticker):
        order: list[PriceProvider] = []
        if TWELVE_KEY:
            order.append("twelve_data")
        if FMP_KEY:
            order.append("fmp")
        if FINNHUB_KEY:
            order.append("finnhub")
        order.extend(["yahoo_chart", "yfinance"])
        return order

    order = []
    if FINNHUB_KEY:
        order.append("finnhub")
    order.append("yahoo_chart")
    if TWELVE_KEY:
        order.append("twelve_data")
    order.append("yfinance")
    return order


def analyst_chain_for(yf_ticker: str) -> list[AnalystProvider]:
    """
    Auto routing:
    - USA: FMP (target price) → Yahoo → Finnhub
    - Internazionale: Yahoo → Finnhub (FMP è solo USA)
    """
    override = (os.environ.get("PRIMARY_ANALYST_API") or "auto").strip().lower()
    if override not in ("", "auto"):
        chain: list[AnalystProvider] = []
        for name in override.split(","):
            n = name.strip()
            if n in ("fmp", "yahoo", "finnhub", "yfinance"):
                chain.append(n)  # type: ignore[arg-type]
        if chain:
            return chain

    if is_us_ticker(yf_ticker):
        order: list[AnalystProvider] = ["yahoo"]
        if FINNHUB_KEY:
            order.append("finnhub")
        if FMP_KEY:
            order.append("fmp")
        order.append("yfinance")
        return order

    order: list[AnalystProvider] = ["yahoo"]
    if FINNHUB_KEY:
        order.append("finnhub")
    order.append("yfinance")
    return order


def primary_price_api_label() -> dict[str, str]:
    """Summary for health UI."""
    us = "yahoo_chart"
    intl = "yahoo_chart"
    if TWELVE_KEY:
        us = "twelve_data"
    elif FMP_KEY:
        us = "fmp"
    elif FINNHUB_KEY:
        us = "finnhub"
    if FINNHUB_KEY:
        intl = "finnhub"
    return {"usa": us, "international": intl}


def primary_analyst_api_label() -> str:
    return "yahoo"


def fetch_price_from_provider(
    provider: PriceProvider,
    yf_ticker: str,
    *,
    fetch_twelve: Callable[[str], pd.Series | None],
    fetch_fmp: Callable[[str], pd.Series | None],
    fetch_finnhub: Callable[[str], pd.Series | None],
    fetch_yahoo: Callable[[str], pd.Series],
    fetch_yfinance: Callable[[str], pd.Series],
) -> tuple[pd.Series, str] | None:
    if provider == "twelve_data":
        s = fetch_twelve(yf_ticker)
        if s is not None and len(s) > 30:
            return s, "twelve_data"
    elif provider == "fmp":
        s = fetch_fmp(yf_ticker)
        if s is not None and len(s) > 30:
            return s, "fmp"
    elif provider == "finnhub":
        s = fetch_finnhub(yf_ticker)
        if s is not None and len(s) > 30:
            return s, "finnhub"
    elif provider == "yahoo_chart":
        try:
            return fetch_yahoo(yf_ticker), "yahoo_chart"
        except Exception:
            pass
    elif provider == "yfinance":
        try:
            return fetch_yfinance(yf_ticker), "yfinance"
        except Exception:
            pass
    return None
