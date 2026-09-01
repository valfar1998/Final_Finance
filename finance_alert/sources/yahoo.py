"""Yahoo Finance chart + RSS: nessuna API key. Non ufficiale, può rompersi."""

from __future__ import annotations

import json
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from finance_alert.http import DEFAULT_UA, get_feed, HttpError, get_json, get_text, map_parallel
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
        if not isinstance(data, dict):
            return None
        block = data["chart"]["result"][0]
        if not isinstance(block, dict):
            return None
    except (
        HttpError,
        OSError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        json.JSONDecodeError,
    ):
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


def _day_key(ts: int, meta: dict) -> str:
    try:
        tz = meta.get("exchangeTimezoneName") or "America/New_York"
        from zoneinfo import ZoneInfo

        when = datetime.fromtimestamp(int(ts), tz=ZoneInfo(str(tz)))
        return when.date().isoformat()
    except (TypeError, ValueError, OSError):
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _slot_key(ts: int, meta: dict) -> str:
    try:
        tz = meta.get("exchangeTimezoneName") or "America/New_York"
        from zoneinfo import ZoneInfo

        when = datetime.fromtimestamp(int(ts), tz=ZoneInfo(str(tz)))
        return when.strftime("%H:%M")
    except (TypeError, ValueError, OSError):
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%H:%M")


def _bar_in_session(ts: int, meta: dict, session: str) -> bool:
    periods = meta.get("currentTradingPeriod") or {}
    pre = periods.get("pre") or {}
    post = periods.get("post") or {}
    regular = periods.get("regular") or {}
    if session == "pre":
        if pre.get("start") is not None and pre.get("end") is not None:
            return int(pre["start"]) <= int(ts) < int(pre["end"])
        return regular.get("start") is not None and int(ts) < int(regular["start"])
    if session == "post":
        if post.get("start") is not None and post.get("end") is not None:
            return int(post["start"]) <= int(ts) < int(post["end"])
        return regular.get("end") is not None and int(ts) >= int(regular["end"])
    if regular.get("start") is not None and regular.get("end") is not None:
        return int(regular["start"]) <= int(ts) < int(regular["end"])
    return False


def _collect_session_series(
    data: Any,
    session: str,
) -> tuple[dict[str, float], dict[str, list[float]]]:
    """Per giorno: volume sessione; per slot HH:MM: lista volumi storici."""
    try:
        block = data["chart"]["result"][0]
        meta = block.get("meta") or {}
        stamps = block.get("timestamp") or []
        volumes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("volume") or []
    except (TypeError, KeyError, IndexError):
        return {}, {}
    day_totals: dict[str, float] = {}
    slot_hist: dict[str, list[float]] = {}
    for ts, vol in zip(stamps, volumes):
        if vol is None:
            continue
        if not _bar_in_session(int(ts), meta, session):
            continue
        day = _day_key(int(ts), meta)
        day_totals[day] = day_totals.get(day, 0.0) + float(vol)
        slot = _slot_key(int(ts), meta)
        slot_hist.setdefault(slot, []).append(float(vol))
    return day_totals, slot_hist


def build_volume_profile(ticker: str, *, range_: str = "1mo", max_days: int = 20) -> dict[str, Any] | None:
    data = _chart_json(ticker, interval="5m", range_=range_)
    if data is None:
        return None
    out: dict[str, Any] = {}
    for session in ("pre", "post", "regular"):
        day_totals, slot_hist = _collect_session_series(data, session)
        if not day_totals:
            continue
        days = sorted(day_totals.keys())[-max_days:]
        totals = [day_totals[d] for d in days if day_totals.get(d, 0) > 0]
        if not totals:
            continue
        slots: dict[str, float] = {}
        for slot, vals in slot_hist.items():
            if vals:
                slots[slot] = sum(vals) / len(vals)
        out[session] = {
            "session_avg": sum(totals) / len(totals),
            "slots": slots,
        }
    return out or None


def fetch_today_session_stats(ticker: str, session: str = "pre") -> tuple[float, list[str]] | None:
    """Volume sessione odierna + slot HH:MM visti (chart 1d only)."""
    data = _chart_json(ticker, interval="5m", range_="1d")
    if data is None:
        return None
    try:
        block = data["chart"]["result"][0]
        meta = block.get("meta") or {}
        stamps = block.get("timestamp") or []
        volumes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("volume") or []
    except (TypeError, KeyError, IndexError):
        return None
    if not stamps:
        return None
    today = _day_key(int(stamps[-1]), meta)
    total = 0.0
    slots: list[str] = []
    for ts, vol in zip(stamps, volumes):
        if vol is None:
            continue
        if _day_key(int(ts), meta) != today:
            continue
        if not _bar_in_session(int(ts), meta, session):
            continue
        total += float(vol)
        key = _slot_key(int(ts), meta)
        if key not in slots:
            slots.append(key)
    if total <= 0:
        return None
    return total, slots


def fetch_rvol(ticker: str, session: str = "pre") -> tuple[float | None, float | None, float | None]:
    """Legacy fallback se baseline assente."""
    data = _chart_json(ticker, interval="5m", range_="5d")
    if data is None:
        return None, None, None
    try:
        block = data["chart"]["result"][0]
        meta = block.get("meta") or {}
        stamps = block.get("timestamp") or []
        volumes = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("volume") or []
    except (TypeError, KeyError, IndexError):
        return None, None, None
    if not stamps:
        return None, None, None

    day_session: dict[str, float] = {}
    for ts, vol in zip(stamps, volumes):
        if vol is None:
            continue
        day = _day_key(int(ts), meta)
        add = 0.0
        if session == "pre":
            periods = meta.get("currentTradingPeriod") or {}
            pre = periods.get("pre") or {}
            regular = periods.get("regular") or {}
            if pre.get("start") is not None and pre.get("end") is not None:
                if int(pre["start"]) <= int(ts) < int(pre["end"]):
                    add = float(vol)
            elif regular.get("start") is not None and int(ts) < int(regular["start"]):
                add = float(vol)
        elif session == "post":
            periods = meta.get("currentTradingPeriod") or {}
            post = periods.get("post") or {}
            regular = periods.get("regular") or {}
            if post.get("start") is not None and post.get("end") is not None:
                if int(post["start"]) <= int(ts) < int(post["end"]):
                    add = float(vol)
            elif regular.get("end") is not None and int(ts) >= int(regular["end"]):
                add = float(vol)
        else:
            periods = meta.get("currentTradingPeriod") or {}
            regular = periods.get("regular") or {}
            if regular.get("start") is not None and regular.get("end") is not None:
                if int(regular["start"]) <= int(ts) < int(regular["end"]):
                    add = float(vol)
        if add:
            day_session[day] = day_session.get(day, 0.0) + add

    if not day_session:
        return None, None, None
    days = sorted(day_session.keys())
    today_vol = day_session.get(days[-1], 0.0)
    hist = [day_session[d] for d in days[:-1] if day_session[d] > 0]
    if not hist or today_vol <= 0:
        return today_vol or None, None, None
    avg = sum(hist) / len(hist)
    if avg <= 0:
        return today_vol, None, None
    return today_vol, avg, today_vol / avg


def fetch_recent_daily_highs(ticker: str, days: int = 20) -> list[float]:
    data = _chart_json(ticker, interval="1d", range_="1mo")
    if data is None:
        return []
    try:
        block = data["chart"]["result"][0]
        highs = ((block.get("indicators") or {}).get("quote") or [{}])[0].get("high") or []
    except (TypeError, KeyError, IndexError):
        return []
    clean = [float(h) for h in highs if h is not None]
    if len(clean) > days:
        clean = clean[-days:]
    return clean


def fetch_daily_ohlc(ticker: str, days: int = 25) -> list[tuple[float, float, float, float]]:
    """Ritorna [(open, high, low, close), ...] per le ultime `days` barre."""
    data = _chart_json(ticker, interval="1d", range_="3mo")
    if data is None:
        return []
    try:
        block = data["chart"]["result"][0]
        quote = ((block.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
    except (TypeError, KeyError, IndexError):
        return []
    rows: list[tuple[float, float, float, float]] = []
    for o, h, l, c in zip(opens, highs, lows, closes):
        if None in (o, h, l, c):
            continue
        rows.append((float(o), float(h), float(l), float(c)))
    if len(rows) > days:
        rows = rows[-days:]
    return rows


def fetch_news(ticker: str) -> list[NewsItem]:
    url = f"{RSS}?{urllib.parse.urlencode({'s': ticker, 'region': 'US', 'lang': 'en-US'})}"
    try:
        xml = get_feed(url, referer="https://finance.yahoo.com/")
        if not xml:
            return []
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
