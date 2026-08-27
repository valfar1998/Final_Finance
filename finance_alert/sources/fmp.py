from __future__ import annotations

import time

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import EarningsEvent, NewsItem, Quote, parse_num

BASE = "https://financialmodelingprep.com/api/v3"


def available() -> bool:
    return bool(env_key("FMP_API_KEY"))


def _key() -> str:
    return env_key("FMP_API_KEY")


def _us(ticker: str) -> str:
    return ticker.split(".")[0].upper()


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not available() or not tickers:
        return {}
    joined = ",".join(_us(t) for t in tickers)
    try:
        data = get_json(f"{BASE}/quote/{joined}", params={"apikey": _key()})
    except (HttpError, OSError, TimeoutError, ValueError):
        return {}
    if not isinstance(data, list):
        return {}
    out: dict[str, Quote] = {}
    by_us = {_us(t): t for t in tickers}
    for row in data:
        if not isinstance(row, dict):
            continue
        us = str(row.get("symbol") or "").upper()
        ticker = by_us.get(us)
        if not ticker:
            continue
        out[ticker] = Quote(
            ticker=ticker,
            price=parse_num(row.get("price")),
            previous_close=parse_num(row.get("previousClose") or row.get("previousClosePrice")),
            change_pct=parse_num(row.get("changesPercentage")),
            source="fmp",
        )
    return out


def fetch_earnings(from_date: str, to_date: str, tickers: list[str]) -> list[EarningsEvent]:
    if not available():
        return []
    wanted = {_us(t) for t in tickers}
    original = {_us(t): t for t in tickers}
    try:
        data = get_json(
            f"{BASE}/earning_calendar",
            params={"from": from_date, "to": to_date, "apikey": _key()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    events: list[EarningsEvent] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        us = str(row.get("symbol") or "").upper()
        if us not in wanted:
            continue
        events.append(
            EarningsEvent(
                ticker=original[us],
                date=str(row.get("date") or "")[:10],
                hour=str(row.get("time") or row.get("hour") or ""),
                eps_actual=parse_num(row.get("eps")),
                eps_estimate=parse_num(row.get("epsEstimated")),
                revenue_actual=parse_num(row.get("revenue")),
                revenue_estimate=parse_num(row.get("revenueEstimated")),
                source="fmp",
            )
        )
    return events


def fetch_news(ticker: str, limit: int = 15) -> list[NewsItem]:
    if not available():
        return []
    try:
        data = get_json(
            f"{BASE}/stock_news",
            params={"tickers": _us(ticker), "limit": limit, "apikey": _key()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items: list[NewsItem] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        if not headline:
            continue
        published = None
        raw = str(row.get("publishedDate") or "")
        if raw:
            try:
                from datetime import datetime

                published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                published = None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("url") or ""),
                published=published,
                source="fmp",
                publisher=str(row.get("site") or row.get("publisher") or ""),
            )
        )
    time.sleep(0.05)
    return items
