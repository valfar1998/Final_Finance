from __future__ import annotations

import time
from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import EarningsEvent, NewsItem, Quote, parse_num

BASE = "https://finnhub.io/api/v1"


def available() -> bool:
    return bool(env_key("FINNHUB_API_KEY"))


def _token() -> str:
    return env_key("FINNHUB_API_KEY")


def fetch_quote(ticker: str) -> Quote | None:
    if not available():
        return None
    try:
        data = get_json(f"{BASE}/quote", params={"symbol": ticker, "token": _token()})
    except (HttpError, OSError, TimeoutError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    price = parse_num(data.get("c"))
    prev = parse_num(data.get("pc"))
    pct = parse_num(data.get("dp"))
    if price in (None, 0) and prev in (None, 0):
        return None
    ts = None
    raw_t = data.get("t")
    if raw_t:
        try:
            ts = datetime.fromtimestamp(int(raw_t), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            ts = None
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=prev,
        change_pct=pct,
        source="finnhub",
        ts=ts,
    )


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    out: dict[str, Quote] = {}
    for i, ticker in enumerate(tickers):
        quote = fetch_quote(ticker)
        if quote:
            out[ticker] = quote
        if i + 1 < len(tickers):
            time.sleep(0.12)
    return out


def fetch_earnings(from_date: str, to_date: str, tickers: list[str]) -> list[EarningsEvent]:
    if not available():
        return []
    wanted = {t.upper() for t in tickers}
    try:
        data = get_json(
            f"{BASE}/calendar/earnings",
            params={"from": from_date, "to": to_date, "token": _token()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = []
    if isinstance(data, dict):
        rows = data.get("earningsCalendar") or []
    events: list[EarningsEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol not in wanted:
            continue
        events.append(
            EarningsEvent(
                ticker=symbol,
                date=str(row.get("date") or "")[:10],
                hour=str(row.get("hour") or ""),
                eps_actual=parse_num(row.get("epsActual")),
                eps_estimate=parse_num(row.get("epsEstimate")),
                revenue_actual=parse_num(row.get("revenueActual")),
                revenue_estimate=parse_num(row.get("revenueEstimate")),
                source="finnhub",
            )
        )
    return events


def fetch_news(ticker: str, from_date: str, to_date: str) -> list[NewsItem]:
    if not available():
        return []
    try:
        data = get_json(
            f"{BASE}/company-news",
            params={
                "symbol": ticker,
                "from": from_date,
                "to": to_date,
                "token": _token(),
            },
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    items: list[NewsItem] = []
    for row in data[:25]:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("headline") or "").strip()
        if not headline:
            continue
        published = None
        if row.get("datetime"):
            try:
                published = datetime.fromtimestamp(int(row["datetime"]), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                published = None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("url") or ""),
                published=published,
                source="finnhub",
                publisher=str(row.get("source") or ""),
            )
        )
    return items
