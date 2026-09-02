"""CLI commands for unified analysis and screening."""

from __future__ import annotations

import json
import sys

from finance_alert.analysis.unified import compute_unified
from finance_alert.config import load_config
from finance_alert.db.store import get_dynamic_watchlist, upsert_watchlist
from finance_alert.env import load_env
from finance_alert.regulatory.hub import detect_region, regulatory_check
from finance_alert.unified_config import load_unified_config


def cmd_analyze(ticker: str) -> int:
    load_env()
    analysis = compute_unified(ticker.upper())
    print("\n".join(analysis.summary_lines()))
    print()
    print(json.dumps(
        {
            "ticker": analysis.ticker,
            "fundamental_score": analysis.fundamental_score,
            "quant_score": analysis.quant_score,
            "unified_score": analysis.unified_score,
            "verdict": analysis.verdict,
            "buy_target_price": analysis.buy_target_price,
            "flags": analysis.flags,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def cmd_regulatory(ticker: str, name: str = "") -> int:
    load_env()
    region = detect_region(ticker)
    profile = regulatory_check(ticker, company_name=name or ticker)
    print(json.dumps(
        {
            "ticker": ticker.upper(),
            "region": region,
            "clean": profile.clean,
            "flags": profile.flags,
            "sources": profile.sources_checked,
            "penalty": profile.score_penalty,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def cmd_screen(*, update_watchlist: bool = False) -> int:
    load_env()
    cfg = load_config()
    ucfg = load_unified_config()
    tickers = list(dict.fromkeys(cfg.symbols + ucfg.rules.screener_tickers))
    results: list[dict] = []
    for ticker in tickers:
        try:
            analysis = compute_unified(ticker)
            row = {
                "ticker": ticker,
                "unified_score": round(analysis.unified_score, 2),
                "fundamental_score": round(analysis.fundamental_score, 1),
                "verdict": analysis.verdict,
                "buy_target": analysis.buy_target_price,
            }
            results.append(row)
            if update_watchlist and analysis.unified_score >= ucfg.rules.screener_min_score:
                upsert_watchlist(ticker, analysis.unified_score)
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)[:120]})
    results.sort(key=lambda x: x.get("unified_score") or 0, reverse=True)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if update_watchlist:
        wl = get_dynamic_watchlist()
        print(f"\nWatchlist dinamica DB: {len(wl)} ticker", file=sys.stderr)
    return 0
