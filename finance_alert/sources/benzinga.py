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
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        if not headline:
            continue
        published = _parse_published(row.get("created") or row.get("updated"))
        author = row.get("author")
        publisher = "Benzinga"
        if isinstance(author, str) and author.strip():
            publisher = f"Benzinga/{author.strip()}"
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("url") or ""),
                published=published,
                source="benzinga",
                publisher=publisher,
            )
        )
    return items
