#!/usr/bin/env python3
"""Scan portfolio tickers, save score history, send Telegram on buyability change."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# bootstrap backend imports
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from load_env import bootstrap_env

bootstrap_env()

from main import analyze_asset  # noqa: E402
from services.portfolio import (  # noqa: E402
    latest_snapshot,
    list_portfolio,
    record_score_snapshot,
)
from services.telegram_alerts import maybe_notify_buyability_change  # noqa: E402


def _asset_from_ticker(row: dict) -> dict:
    yf = row.get("yf_ticker") or row["ticker"]
    return {
        "id": row["ticker"].lower(),
        "name": row.get("name") or yf,
        "type": "azione",
        "stooq": f"{yf.lower()}.us" if "." not in yf else yf.lower(),
        "yf": yf,
        "region": "usa",
        "country": "USA",
        "startup": False,
    }


def scan(*, notify: bool = True) -> list[dict]:
    portfolio = list_portfolio()
    if not portfolio:
        return [{"error": "portafogio vuoto — POST /api/portfolio con ticker"}]
    results: list[dict] = []
    for row in portfolio:
        ticker = row["ticker"]
        prev = latest_snapshot(ticker)
        old_buy = float(prev["buyability_pct"]) if prev and prev.get("buyability_pct") is not None else None
        try:
            analysis = analyze_asset(_asset_from_ticker(row), include_chart=False, use_cache=False)
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})
            continue
        record_score_snapshot(ticker, analysis)
        new_buy = analysis.get("buyability_pct")
        sent = False
        if notify:
            sent = maybe_notify_buyability_change(
                ticker,
                name=analysis.get("name") or ticker,
                old_buy=old_buy,
                new_buy=new_buy,
                price=analysis.get("current_price"),
                forecast_pct=analysis.get("previsione_rendimento_pct"),
            )
        results.append(
            {
                "ticker": ticker,
                "buyability_pct": new_buy,
                "previsione_rendimento_pct": analysis.get("previsione_rendimento_pct"),
                "current_price": analysis.get("current_price"),
                "notified": sent,
                "prev_buyability": old_buy,
            }
        )
    return results


if __name__ == "__main__":
    notify = "--no-notify" not in sys.argv
    print(json.dumps(scan(notify=notify), indent=2, ensure_ascii=False, default=str))
