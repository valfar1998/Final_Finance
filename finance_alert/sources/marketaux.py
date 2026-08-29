"""Marketaux — news finanziarie con ticker taggati (piano free limitato)."""

from __future__ import annotations

from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import NewsItem

BASE = "https://api.marketaux.com/v1/news/all"


def available() -> bool:
    return bool(env_key("MARKETAUX_API_TOKEN"))


def fetch_news(ticker: str, *, limit: int = 15) -> list[NewsItem]:
    if not available():
        return []
    us = ticker.split(".")[0].upper()
    try:
        data = get_json(
            BASE,
            params={
                "symbols": us,
                "filter_entities": "true",
                "language": "en",
                "limit": limit,
                "api_token": env_key("MARKETAUX_API_TOKEN"),
            },
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("data") or []
    if not isinstance(rows, list):
        return []
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        if not headline:
            continue
        published = None
        raw = str(row.get("published_at") or "")
        if raw:
            try:
                published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except ValueError:
                published = None
        source_block = row.get("source")
        publisher = ""
        if isinstance(source_block, str):
            publisher = source_block
        elif isinstance(source_block, dict):
            publisher = str(source_block.get("name") or "")
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("url") or ""),
                published=published,
                source="marketaux",
                publisher=publisher,
            )
        )
    return items
