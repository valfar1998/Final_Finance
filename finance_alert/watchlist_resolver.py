"""Unisce watchlist statica, screener globale e watchlist dinamica SQLite."""

from __future__ import annotations

from finance_alert.config import AppConfig, Ticker, load_config
from finance_alert.db.store import get_dynamic_watchlist
from finance_alert.unified_config import load_unified_config


def resolve_scan_symbols(cfg: AppConfig | None = None) -> tuple[list[str], list[Ticker]]:
    """
    Ritorna (symbols, watchlist_ticker_objects) per il prossimo scan.
    Ordine: YAML → screener_tickers → dynamic_watchlist (deduplicati).
    """
    cfg = cfg or load_config()
    ucfg = load_unified_config()
    rules = ucfg.rules

    seen: set[str] = set()
    ordered: list[str] = []
    ticker_map: dict[str, Ticker] = {t.ticker: t for t in cfg.watchlist}

    def add(sym: str) -> None:
        up = sym.strip().upper()
        if not up or up in seen:
            return
        seen.add(up)
        ordered.append(up)
        if up not in ticker_map:
            ticker_map[up] = Ticker(ticker=up)

    for t in cfg.watchlist:
        add(t.ticker)

    if rules.include_global_screener:
        for sym in rules.screener_tickers:
            add(sym)

    if rules.use_dynamic_watchlist:
        for sym in get_dynamic_watchlist(min_score=rules.dynamic_min_score):
            add(sym)

    cap = rules.max_scan_symbols
    if cap > 0 and len(ordered) > cap:
        ordered = ordered[:cap]

    watchlist = [ticker_map[s] for s in ordered]
    return ordered, watchlist
