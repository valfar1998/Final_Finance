"""Unisce watchlist statica, screener globale, dynamic SQLite e universo premarket gratis."""

from __future__ import annotations

from finance_alert.config import AppConfig, Ticker, load_config
from finance_alert.db.store import get_dynamic_watchlist
from finance_alert.premarket_universe import discover_hot_symbols
from finance_alert.unified_config import load_unified_config


def resolve_scan_symbols(cfg: AppConfig | None = None) -> tuple[list[str], list[Ticker]]:
    """
    Ritorna (symbols, watchlist_ticker_objects) per il prossimo scan.
    Ordine: YAML → screener_tickers → dynamic_watchlist → premarket hot (deduplicati).
    La watchlist YAML non viene tagliata: gli extra entrano solo se c'è spazio sotto max_scan_symbols.
    """
    cfg = cfg or load_config()
    ucfg = load_unified_config()
    rules = ucfg.rules

    seen: set[str] = set()
    ordered: list[str] = []
    ticker_map: dict[str, Ticker] = {t.ticker: t for t in cfg.watchlist}

    def add(sym: str) -> bool:
        up = sym.strip().upper()
        if not up or up in seen:
            return False
        seen.add(up)
        ordered.append(up)
        if up not in ticker_map:
            ticker_map[up] = Ticker(ticker=up)
        return True

    for t in cfg.watchlist:
        add(t.ticker)

    core_n = len(ordered)

    if rules.include_global_screener:
        for sym in rules.screener_tickers:
            add(sym)

    if rules.use_dynamic_watchlist:
        for sym in get_dynamic_watchlist(min_score=rules.dynamic_min_score):
            add(sym)

    # Premarket: solo slot residuali sotto il cap (non toglie titoli dalla watchlist)
    cap = rules.max_scan_symbols
    if cfg.rules.premarket.enabled:
        room = max(0, (cap - len(ordered)) if cap > 0 else cfg.rules.premarket.max_extra)
        room = min(room, cfg.rules.premarket.max_extra)
        if room > 0:
            discovery = discover_hot_symbols(cfg.rules.premarket)
            added = 0
            for sym in discovery.merged:
                if added >= room:
                    break
                if add(sym):
                    added += 1

    if cap > 0 and len(ordered) > cap:
        # Proteggi i primi core_n (YAML); taglia solo gli extra se serve
        if core_n >= cap:
            ordered = ordered[:cap]
        else:
            ordered = ordered[:cap]

    watchlist = [ticker_map[s] for s in ordered]
    return ordered, watchlist
