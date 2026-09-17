"""Alpha Vantage — quote + news (free tier: pochi req/giorno, usare come fallback)."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import NewsItem, Quote, is_quoteable_ticker, parse_num

BASE = "https://www.alphavantage.co/query"
# Free tier recente ≈ 25 req/giorno: serializza e limita.
_MIN_INTERVAL_SEC = 12.5
_MAX_QUOTE_PER_RUN = 8
_MAX_NEWS_TICKERS = 5
_last_call_ts = 0.0


def available() -> bool:
    return bool(env_key("ALPHA_VANTAGE_API_KEY"))


def _token() -> str:
    return env_key("ALPHA_VANTAGE_API_KEY")


def _throttle() -> None:
    global _last_call_ts
    now = time.monotonic()
    wait = _MIN_INTERVAL_SEC - (now - _last_call_ts)
    if wait > 0:
        time.sleep(wait)
    _last_call_ts = time.monotonic()


def _query(params: dict) -> dict | list | None:
    if not available():
        return None
    payload = {**params, "apikey": _token()}
    _throttle()
    try:
        data = get_json(BASE, params=payload, timeout=25.0, retries=1)
    except (HttpError, OSError, TimeoutError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    # Rate limit / premium notice
    if data.get("Note") or data.get("Information") or data.get("Error Message"):
        return None
    return data


def fetch_quote(ticker: str) -> Quote | None:
    """GLOBAL_QUOTE — 1 richiesta per ticker."""
    us = ticker.split(".")[0].upper()
    if not is_quoteable_ticker(us):
        return None
    data = _query({"function": "GLOBAL_QUOTE", "symbol": us})
    if not isinstance(data, dict):
        return None
    row = data.get("Global Quote") or data.get("globalQuote") or {}
    if not isinstance(row, dict) or not row:
        return None
    price = parse_num(row.get("05. price") or row.get("price"))
    prev = parse_num(row.get("08. previous close") or row.get("previous_close"))
    change_pct = parse_num(
        str(row.get("10. change percent") or row.get("change_percent") or "")
        .replace("%", "")
        .strip()
        or None
    )
    if price in (None, 0) and prev in (None, 0):
        return None
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=prev,
        change_pct=change_pct,
        source="alpha_vantage",
        volume=parse_num(row.get("06. volume") or row.get("volume")),
    )


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    """Fallback selettivo: max N ticker per run per non esaurire la quota free."""
    if not available() or not tickers:
        return {}
    clean = [t for t in tickers if is_quoteable_ticker(t)][:_MAX_QUOTE_PER_RUN]
    out: dict[str, Quote] = {}
    for ticker in clean:
        q = fetch_quote(ticker)
        if q is not None:
            out[ticker] = q
    return out


def _parse_av_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    # NEWS_SENTIMENT: 20240917T163000
    if len(text) >= 15 and text[8:9] == "T" and text[:8].isdigit():
        try:
            return datetime.strptime(text[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def fetch_news(ticker: str, *, limit: int = 8) -> list[NewsItem]:
    """NEWS_SENTIMENT filtrato sul ticker."""
    us = ticker.split(".")[0].upper()
    if not available() or not is_quoteable_ticker(us):
        return []
    data = _query(
        {
            "function": "NEWS_SENTIMENT",
            "tickers": us,
            "limit": min(max(limit, 1), 50),
            "sort": "LATEST",
        }
    )
    if not isinstance(data, dict):
        return []
    rows = data.get("feed") or []
    out: list[NewsItem] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not headline:
            continue
        out.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=url,
                published=_parse_av_time(str(row.get("time_published") or "")),
                source="alpha_vantage",
                publisher=str(row.get("source") or "Alpha Vantage"),
            )
        )
    return out


def fetch_market_news(*, limit: int = 20) -> list[NewsItem]:
    """News di mercato generiche (topics=financial_markets). 1 richiesta."""
    if not available():
        return []
    data = _query(
        {
            "function": "NEWS_SENTIMENT",
            "topics": "financial_markets",
            "limit": min(max(limit, 1), 50),
            "sort": "LATEST",
        }
    )
    if not isinstance(data, dict):
        return []
    rows = data.get("feed") or []
    out: list[NewsItem] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not headline:
            continue
        tickers = row.get("ticker_sentiment") or []
        sym = ""
        if isinstance(tickers, list) and tickers:
            first = tickers[0] if isinstance(tickers[0], dict) else {}
            sym = str(first.get("ticker") or "").upper()
        out.append(
            NewsItem(
                ticker=sym,
                headline=headline,
                url=url,
                published=_parse_av_time(str(row.get("time_published") or "")),
                source="alpha_vantage",
                publisher=str(row.get("source") or "Alpha Vantage"),
            )
        )
    return out
