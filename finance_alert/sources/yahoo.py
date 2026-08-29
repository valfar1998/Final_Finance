"""Yahoo Finance chart + RSS: nessuna API key. Non ufficiale, può rompersi."""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from finance_alert.http import DEFAULT_UA, HttpError, get_json, get_text, map_parallel
from finance_alert.models import NewsItem, Quote, parse_num

CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline"

# Cache breve delle risposte chart (session + momentum condividono le barre 5m).
_CHART_TTL_SEC = 55.0
_chart_cache: dict[tuple[str, str, str], tuple[float, Any]] = {}


def _chart_json(ticker: str, *, interval: str, range_: str) -> Any | None:
    key = (ticker.upper(), interval, range_)
    now = time.time()
    hit = _chart_cache.get(key)
    if hit and now - hit[0] < _CHART_TTL_SEC:
        return hit[1]
    try:
        data = get_json(
            CHART.format(ticker=ticker),
            params={"interval": interval, "range": range_, "includePrePost": "true"},
            headers={"User-Agent": DEFAULT_UA, "Referer": "https://finance.yahoo.com/"},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return None
    _chart_cache[key] = (now, data)
    return data


def fetch_quote(ticker: str) -> Quote | None:
    data = _chart_json(ticker, interval="1d", range_="5d")
    if data is None:
        return None
    try:
        block = data["chart"]["result"][0]
    except (TypeError, KeyError, IndexError):
        return None
    meta = block.get("meta") or {}
    price = parse_num(meta.get("regularMarketPrice") or meta.get("postMarketPrice"))
    prev = parse_num(meta.get("previousClose") or meta.get("chartPreviousClose"))
    if price is None:
        quotes = ((block.get("indicators") or {}).get("quote") or [{}])[0]
        closes = [c for c in (quotes.get("close") or []) if c is not None]
        if closes:
            price = float(closes[-1])
        if prev is None and len(closes) >= 2:
            prev = float(closes[-2])
    if price is None:
        return None
    pct = None
    if prev:
        pct = (price - prev) / prev * 100.0
    ts = None
    if meta.get("regularMarketTime"):
        try:
            ts = datetime.fromtimestamp(int(meta["regularMarketTime"]), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            ts = None
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=prev,
        change_pct=pct,
        source="yahoo_chart",
        ts=ts,
    )


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not tickers:
        return {}
    results = map_parallel(fetch_quote, tickers, max_workers=min(6, len(tickers)))
    return {q.ticker: q for q in results if q is not None}


def _session_from_meta(meta: dict, now_ts: int) -> str:
    periods = meta.get("currentTradingPeriod") or {}
    pre = periods.get("pre") or {}
    regular = periods.get("regular") or {}
    post = periods.get("post") or {}
    if pre.get("start") is not None and pre.get("end") is not None:
        if int(pre["start"]) <= now_ts < int(pre["end"]):
            return "pre"
    if post.get("start") is not None and post.get("end") is not None:
        if int(post["start"]) <= now_ts < int(post["end"]):
            return "post"
    if regular.get("start") is not None and now_ts < int(regular["start"]):
        return "pre"
    if regular.get("end") is not None and now_ts >= int(regular["end"]):
        return "post"
    return "regular"


def fetch_session_quote(ticker: str) -> Quote | None:
    """Pre-market / after-hours vs chiusura precedente (barre 5 min + prepost)."""
    data = _chart_json(ticker, interval="5m", range_="1d")
    if data is None:
        return None
    try:
        block = data["chart"]["result"][0]
    except (TypeError, KeyError, IndexError):
        return None
    meta = block.get("meta") or {}
    now_ts = int(time.time())
    session = _session_from_meta(meta, now_ts)
    prev = parse_num(meta.get("previousClose") or meta.get("chartPreviousClose"))
    price = parse_num(meta.get("regularMarketPrice"))
    stamps = block.get("timestamp") or []
    closes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    last = None
    last_ts = None
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        last = float(close)
        last_ts = int(ts)
    if session in {"pre", "post"} and last is not None:
        price = last
    if price is None:
        return None
    pct = None
    if prev:
        pct = (price - prev) / prev * 100.0
    ts = None
    if last_ts:
        try:
            ts = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            ts = None
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=prev,
        change_pct=pct,
        source="yahoo_ext",
        ts=ts,
        session=session,
    )


def fetch_session_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not tickers:
        return {}
    results = map_parallel(fetch_session_quote, tickers, max_workers=min(6, len(tickers)))
    return {q.ticker: q for q in results if q is not None}


def fetch_momentum_pct(ticker: str, minutes: int = 30) -> float | None:
    """Variazione % sulle ultime N minuti (barre 5m)."""
    data = _chart_json(ticker, interval="5m", range_="1d")
    if data is None:
        return None
    try:
        block = data["chart"]["result"][0]
        stamps = block.get("timestamp") or []
        closes = (block["indicators"]["quote"][0].get("close") or [])
    except (TypeError, KeyError, IndexError):
        return None
    pairs: list[tuple[datetime, float]] = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        try:
            when = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            continue
        pairs.append((when, float(close)))
    if len(pairs) < 2:
        return None
    latest_ts, latest = pairs[-1]
    cutoff = latest_ts - timedelta(minutes=minutes)
    earlier = pairs[0][1]
    for when, close in pairs:
        if when >= cutoff:
            break
        earlier = close
    if not earlier:
        return None
    return (latest - earlier) / earlier * 100.0


def fetch_news(ticker: str) -> list[NewsItem]:
    try:
        xml = get_text(
            RSS,
            params={"s": ticker, "region": "US", "lang": "en-US"},
            headers={"User-Agent": DEFAULT_UA},
        )
    except (HttpError, OSError, TimeoutError):
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    items: list[NewsItem] = []
    for node in root.findall("./channel/item")[:20]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        if not title:
            continue
        published = None
        pub = node.findtext("pubDate")
        if pub:
            try:
                published = parsedate_to_datetime(pub)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                published = None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=title,
                url=link,
                published=published,
                source="yahoo_rss",
                publisher="Yahoo",
            )
        )
    return items
