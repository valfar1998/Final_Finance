"""NewsAPI.org — headline aggregator (developer free: ~100 req/giorno)."""

from __future__ import annotations

from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import NewsItem

BASE = "https://newsapi.org/v2/everything"


def available() -> bool:
    return bool(env_key("NEWSAPI_API_KEY"))


def fetch_news(ticker: str, from_date: str, *, page_size: int = 15) -> list[NewsItem]:
    if not available():
        return []
    # Query ticker + nome comune (es. NVDA → anche NVIDIA via OR ticker)
    q = ticker.split(".")[0].upper()
    try:
        data = get_json(
            BASE,
            params={
                "q": q,
                "from": from_date,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": env_key("NEWSAPI_API_KEY"),
            },
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("status") != "ok":
        return []
    rows = data.get("articles") or []
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        if not headline or headline.upper() == "[REMOVED]":
            continue
        published = None
        raw = str(row.get("publishedAt") or "")
        if raw:
            try:
                published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except ValueError:
                published = None
        source_block = row.get("source") if isinstance(row.get("source"), dict) else {}
        publisher = str((source_block or {}).get("name") or row.get("author") or "")
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("url") or ""),
                published=published,
                source="newsapi",
                publisher=publisher,
            )
        )
    return items
