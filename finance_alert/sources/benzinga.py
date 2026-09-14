"""Benzinga Newsfeed — wire finanziario in tempo reale."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import NewsItem

BASE = "https://api.benzinga.com/api/v2/news"


def available() -> bool:
    return bool(env_key("BENZINGA_API_TOKEN"))


def _parse_published(raw: object) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError, IndexError):
        return None


def fetch_news(ticker: str, *, page_size: int = 15) -> list[NewsItem]:
    if not available():
        return []
    us = ticker.split(".")[0].upper()
    try:
        data = get_json(
            BASE,
            params={
                "token": env_key("BENZINGA_API_TOKEN"),
                "tickers": us,
                "pageSize": page_size,
                "displayOutput": "headline",
            },
            headers={"Accept": "application/json"},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = data if isinstance(data, list) else []
    items: list[NewsItem] = []
    for row in rows:
        item = _row_to_item(row, fallback_ticker=ticker)
        if item:
            items.append(item)
    return items


def _row_to_item(row: dict, *, fallback_ticker: str = "") -> NewsItem | None:
    if not isinstance(row, dict):
        return None
    headline = str(row.get("title") or "").strip()
    if not headline:
        return None
    published = _parse_published(row.get("created") or row.get("updated"))
    author = row.get("author")
    publisher = "Benzinga"
    if isinstance(author, str) and author.strip():
        publisher = f"Benzinga/{author.strip()}"
    tickers: list[str] = []
    stocks = row.get("stocks")
    if isinstance(stocks, list):
        for stock in stocks:
            if isinstance(stock, dict):
                name = str(stock.get("name") or "").strip().upper()
                if name:
                    tickers.append(name)
            elif isinstance(stock, str) and stock.strip():
                tickers.append(stock.strip().upper())
    fb = fallback_ticker.strip().upper()
    ticker = fb if fb else (tickers[0] if tickers else "")
    if not ticker:
        return None
    return NewsItem(
        ticker=ticker,
        headline=headline,
        url=str(row.get("url") or ""),
        published=published,
        source="benzinga",
        publisher=publisher,
    )


def fetch_latest_news(*, page_size: int = 50) -> list[NewsItem]:
    """Ultime headline Benzinga (multi-ticker) — priorità massima per scarto basso."""
    if not available():
        return []
    try:
        data = get_json(
            BASE,
            params={
                "token": env_key("BENZINGA_API_TOKEN"),
                "pageSize": min(int(page_size), 100),
                "displayOutput": "headline",
            },
            headers={"Accept": "application/json"},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = data if isinstance(data, list) else []
    items: list[NewsItem] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        stocks = row.get("stocks")
        tickers: list[str] = []
        if isinstance(stocks, list):
            for stock in stocks:
                if isinstance(stock, dict):
                    name = str(stock.get("name") or "").strip().upper()
                    if name:
                        tickers.append(name)
        if not tickers:
            item = _row_to_item(row)
            if item:
                key = (item.url or item.headline).lower()
                if key not in seen:
                    seen.add(key)
                    items.append(item)
            continue
        # Una news per ogni ticker taggato (upgrade spesso tocca un cluster)
        for tick in tickers[:6]:
            item = _row_to_item(row, fallback_ticker=tick)
            if item is None:
                continue
            key = f"{tick}|{(item.url or item.headline).lower()}"
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
    return items
