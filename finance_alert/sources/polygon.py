from __future__ import annotations

from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import NewsItem, Quote, parse_num

BASE = "https://api.polygon.io"


def available() -> bool:
    return bool(env_key("POLYGON_API_KEY"))


def _key() -> str:
    return env_key("POLYGON_API_KEY")


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not available():
        return {}
    out: dict[str, Quote] = {}
    for ticker in tickers:
        us = ticker.split(".")[0].upper()
        try:
            data = get_json(
                f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{us}",
                params={"apiKey": _key()},
            )
        except (HttpError, OSError, TimeoutError, ValueError):
            continue
        ticker_block = (data or {}).get("ticker") if isinstance(data, dict) else None
        if not isinstance(ticker_block, dict):
            continue
        day = ticker_block.get("day") or {}
        prev = ticker_block.get("prevDay") or {}
        last = ticker_block.get("lastTrade") or ticker_block.get("min") or {}
        price = parse_num(last.get("p") or day.get("c"))
        previous = parse_num(prev.get("c"))
        pct = parse_num(ticker_block.get("todaysChangePerc"))
        if price is None:
            continue
        out[ticker] = Quote(
            ticker=ticker,
            price=price,
            previous_close=previous,
            change_pct=pct,
            source="polygon",
        )
    return out


def fetch_news(ticker: str, limit: int = 15) -> list[NewsItem]:
    if not available():
        return []
    us = ticker.split(".")[0].upper()
    try:
        data = get_json(
            f"{BASE}/v2/reference/news",
            params={"ticker": us, "limit": limit, "apiKey": _key()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = (data or {}).get("results") if isinstance(data, dict) else None
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
        raw = str(row.get("published_utc") or "")
        if raw:
            try:
                published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                published = None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("article_url") or ""),
                published=published,
                source="polygon",
                publisher=str(row.get("publisher", {}).get("name") if isinstance(row.get("publisher"), dict) else row.get("author") or ""),
            )
        )
    return items
