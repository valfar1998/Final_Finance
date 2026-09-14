"""Universo premarket gratuito: Yahoo screener + Polygon grouped daily (no snapshot live)."""

from __future__ import annotations

from dataclasses import dataclass

from finance_alert.config import PremarketRules
from finance_alert.sources import polygon, yahoo


@dataclass(frozen=True)
class PremarketDiscovery:
    yahoo: list[str]
    polygon: list[str]
    merged: list[str]


def discover_hot_symbols(rules: PremarketRules) -> PremarketDiscovery:
    """Ritorna candidati extra (non ancora filtrati contro la watchlist)."""
    if not rules.enabled or rules.max_extra <= 0:
        return PremarketDiscovery(yahoo=[], polygon=[], merged=[])

    yahoo_syms: list[str] = []
    if rules.yahoo_enabled:
        yahoo_syms = yahoo.fetch_screener_symbols(
            rules.yahoo_screens,
            count=rules.yahoo_count_per_screen,
        )

    poly_syms: list[str] = []
    if rules.polygon_enabled and polygon.available():
        poly_syms = polygon.fetch_prev_day_movers(
            min_abs_pct=rules.polygon_min_pct,
            min_volume=rules.polygon_min_volume,
            min_price=rules.polygon_min_price,
            limit=rules.max_extra,
            upside_only=rules.upside_only,
        )

    # Priorità: Yahoo (live-ish screener) poi Polygon (EOD giorno prima)
    seen: set[str] = set()
    merged: list[str] = []
    for sym in yahoo_syms + poly_syms:
        up = sym.strip().upper()
        if not up or up in seen:
            continue
        seen.add(up)
        merged.append(up)
        if len(merged) >= rules.max_extra:
            break
    return PremarketDiscovery(yahoo=yahoo_syms, polygon=poly_syms, merged=merged)
