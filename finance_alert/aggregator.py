"""Sceglie la prima fonte disponibile e riempie i buchi con i fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from finance_alert.config import AppConfig
from finance_alert.http import map_parallel
from finance_alert.models import EarningsEvent, Filing, NewsItem, Quote
from finance_alert.sources import benzinga, edgar, finnhub, fmp, marketaux, newsapi, polygon, twelve, yahoo


def source_status() -> dict[str, bool]:
    from finance_alert.news_llm import llm_available

    return {
        "finnhub": finnhub.available(),
        "fmp": fmp.available(),
        "twelve_data": twelve.available(),
        "polygon": polygon.available(),
        "benzinga": benzinga.available(),
        "newsapi": newsapi.available(),
        "marketaux": marketaux.available(),
        "news_llm": llm_available(),
        "yahoo_chart": True,
        "sec_edgar": True,
        "yahoo_rss": True,
    }


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    """Preferisce provider batch (FMP/Twelve), poi Finnhub/Polygon, Yahoo ultima rete."""
    merged: dict[str, Quote] = {}
    providers = []
    # Batch-first: 1 HTTP per tutta la watchlist
    if fmp.available():
        providers.append(("fmp", fmp.fetch_quotes))
    if twelve.available():
        providers.append(("twelve", twelve.fetch_quotes))
    if finnhub.available():
        providers.append(("finnhub", finnhub.fetch_quotes))
    if polygon.available():
        providers.append(("polygon", polygon.fetch_quotes))
    providers.append(("yahoo", yahoo.fetch_quotes))

    missing = list(tickers)
    for _name, fn in providers:
        if not missing:
            break
        got = fn(missing)
        for ticker, quote in got.items():
            if ticker not in merged:
                merged[ticker] = quote
        missing = [t for t in tickers if t not in merged]
    return merged


def overlay_extended_hours(quotes: dict[str, Quote], tickers: list[str]) -> dict[str, Quote]:
    """Sovrascrive prezzo/% in pre/after-hours (Yahoo 5m). Così si anticipa l'open USA."""
    ext = yahoo.fetch_session_quotes(tickers)
    for ticker, session_q in ext.items():
        base = quotes.get(ticker)
        if base is None:
            quotes[ticker] = session_q
            continue
        base.session = session_q.session
        if session_q.session in {"pre", "post"}:
            if session_q.price is not None:
                base.price = session_q.price
            if session_q.change_pct is not None:
                base.change_pct = session_q.change_pct
            if session_q.previous_close is not None:
                base.previous_close = session_q.previous_close
            base.source = f"{base.source}+yahoo_ext"
            base.ts = session_q.ts or base.ts
    return quotes


def overlay_volume_stats(quotes: dict[str, Quote]) -> dict[str, Quote]:
    tickers = list(quotes.keys())
    if not tickers:
        return quotes

    def _attach(ticker: str) -> tuple[str, float | None, float | None, float | None]:
        q = quotes[ticker]
        session = (q.session or "regular").lower()
        sess = session if session in {"pre", "post"} else "regular"
        return ticker, *yahoo.fetch_rvol(ticker, session=sess)

    for ticker, vol, avg, rvol in map_parallel(_attach, tickers, max_workers=min(6, len(tickers))):
        q = quotes.get(ticker)
        if q is None:
            continue
        q.volume = vol
        q.avg_volume = avg
        q.rvol = rvol
    return quotes


def fetch_earnings(cfg: AppConfig, now: datetime) -> list[EarningsEvent]:
    today = now.date()
    frm = (today - timedelta(days=1)).isoformat()
    to = (today + timedelta(days=2)).isoformat()
    events: list[EarningsEvent] = []
    if finnhub.available():
        events = finnhub.fetch_earnings(frm, to, cfg.symbols)
    if not events and fmp.available():
        events = fmp.fetch_earnings(frm, to, cfg.symbols)
    return events


def _dedupe_news(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for item in items:
        key = (item.url or item.headline).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _news_for_ticker(args: tuple[str, str, str]) -> list[NewsItem]:
    ticker, frm, to = args
    batch: list[NewsItem] = []
    if benzinga.available():
        batch.extend(benzinga.fetch_news(ticker))
    if finnhub.available():
        batch.extend(finnhub.fetch_news(ticker, frm, to))
    if polygon.available() and len(batch) < 5:
        batch.extend(polygon.fetch_news(ticker))
    if marketaux.available() and len(batch) < 8:
        batch.extend(marketaux.fetch_news(ticker))
    if newsapi.available() and len(batch) < 8:
        batch.extend(newsapi.fetch_news(ticker, frm))
    if fmp.available() and len(batch) < 5:
        batch.extend(fmp.fetch_news(ticker))
    if len(batch) < 3:
        batch.extend(yahoo.fetch_news(ticker))
    return batch


def fetch_news(cfg: AppConfig, now: datetime) -> list[NewsItem]:
    today = now.date()
    frm = (today - timedelta(days=1)).isoformat()
    to = today.isoformat()
    jobs = [(ticker, frm, to) for ticker in cfg.symbols]
    batches = map_parallel(_news_for_ticker, jobs, max_workers=min(6, max(1, len(jobs))))
    items: list[NewsItem] = []
    for batch in batches:
        items.extend(batch)
    cutoff = now.astimezone(timezone.utc) - timedelta(hours=cfg.rules.news_max_age_hours)
    fresh: list[NewsItem] = []
    for item in _dedupe_news(items):
        if item.published and item.published.tzinfo is None:
            item.published = item.published.replace(tzinfo=timezone.utc)
        if item.published and item.published < cutoff:
            continue
        fresh.append(item)
    return fresh


def fetch_momentum(tickers: list[str], minutes: int) -> dict[str, float]:
    def _one(ticker: str) -> tuple[str, float | None]:
        return ticker, yahoo.fetch_momentum_pct(ticker, minutes=minutes)

    results = map_parallel(_one, tickers, max_workers=min(6, max(1, len(tickers))))
    return {t: pct for t, pct in results if pct is not None}


def fetch_filings(cfg: AppConfig) -> list[Filing]:
    if not cfg.edgar.enabled:
        return []
    return edgar.fetch_filings(cfg.watchlist, cfg.edgar.forms)
