"""Salvaguardia macro: mercato in stress → soglia setup più alta."""

from __future__ import annotations

from finance_alert.config import MacroRules
from finance_alert.models import Quote


def fetch_index_moves(tickers: list[str], quotes: dict[str, Quote]) -> dict[str, float]:
    out: dict[str, float] = {}
    for sym in tickers:
        q = quotes.get(sym.upper())
        if q is None:
            continue
        pct = q.pct_from_close()
        if pct is not None:
            out[sym.upper()] = pct
    return out


def effective_min_setup_score(rules_macro: MacroRules, index_moves: dict[str, float]) -> int:
    if not rules_macro.enabled or not index_moves:
        return rules_macro.normal_min_setup_score
    worst = min(index_moves.values())
    if worst <= rules_macro.stress_pct:
        return rules_macro.stressed_min_setup_score
    return rules_macro.normal_min_setup_score
