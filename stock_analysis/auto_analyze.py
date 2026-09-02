#!/usr/bin/env python3
"""
Analisi automatica solo via API (yfinance) — niente upload HTML.
Equivalente al percorso "10/10" del brief: dati Yahoo + scoring settoriale.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

NOT_AVAILABLE = "non disponibile"

from portfolio_db import add_ticker, latest_score, list_portfolio, save_score
from telegram_notify import maybe_notify
from yahoo_api import fetch_yahoo_metrics, normalize_ticker


def _guess_sector(metrics: dict) -> str:
    sector = str(metrics.get("sector") or metrics.get("industry") or "").upper()
    if "REAL ESTATE" in sector:
        return "REIT"
    if "FINANCIAL" in sector:
        return "FINANCIALS"
    if "TECH" in sector:
        return "TECH"
    if "HEALTH" in sector:
        return "HEALTHCARE"
    if "ENERGY" in sector or "UTILIT" in sector:
        return "ENERGY"
    if "CONSUMER" in sector:
        return "CONSUMER"
    if "INDUSTRIAL" in sector:
        return "INDUSTRIAL"
    if "COMMUNICATION" in sector:
        return "COMMUNICATION"
    return "GENERICO"


def _parse_buy_price(text: str) -> float | None:
    m = re.search(r"\$(\d+(?:\.\d+)?)", text or "")
    return float(m.group(1)) if m else None


def analyze_auto(ticker: str, *, sector: str | None = None) -> dict:
    from scoring_engine import buy_target, run_analysis

    t = normalize_ticker(ticker)
    metrics = fetch_yahoo_metrics(t)
    sec = sector or _guess_sector(metrics)
    result = run_analysis(NOT_AVAILABLE, NOT_AVAILABLE, sec, yahoo_metrics=metrics)
    score = float(result["score"])
    reliable = bool(result["reliable"])
    target_txt = buy_target(metrics, sec, score, reliable)
    buy_price = _parse_buy_price(target_txt)
    price = metrics.get("price")
    if buy_price and price and buy_price < price * 0.5:
        if score >= 80:
            buy_price = round(price * 0.95, 2)
        elif score >= 60:
            buy_price = round(price * 0.90, 2)
        elif score >= 40:
            buy_price = round(price * 0.85, 2)
        else:
            buy_price = round(price * 0.75, 2)
    return {
        "ticker": t,
        "sector": sec,
        "score": score,
        "verdict": result["verdict"],
        "reliable": reliable,
        "price": price,
        "buy_target_text": target_txt,
        "buy_target_price": buy_price,
        "report": result["report"],
    }


def scan_portfolio(*, notify: bool = True, add_missing: bool = False) -> list[dict]:
    tickers = list_portfolio()
    if not tickers and add_missing:
        for sym in ("NVDA", "AAPL", "PLTR"):
            add_ticker(sym)
        tickers = list_portfolio()
    results: list[dict] = []
    for row in tickers:
        ticker = row["ticker"]
        prev = latest_score(ticker)
        old_score = float(prev["score"]) if prev and prev.get("score") is not None else None
        try:
            analysis = analyze_auto(ticker, sector=row.get("sector"))
        except Exception as exc:
            results.append({"ticker": ticker, "error": str(exc)})
            continue
        save_score(ticker, analysis)
        sent = False
        if notify:
            sent = maybe_notify(
                ticker,
                old_score=old_score,
                new_score=analysis["score"],
                verdict=analysis["verdict"],
                buy_target=analysis.get("buy_target_price"),
            )
        results.append({**analysis, "notified": sent, "prev_score": old_score})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analisi automatica Yahoo + portafoglio")
    parser.add_argument("ticker", nargs="?", help="Singolo ticker (es. GOOGL)")
    parser.add_argument("--sector", default=None, help="Settore scoring (TECH, REIT, …)")
    parser.add_argument("--scan", action="store_true", help="Scansiona tutto il portafoglio DB")
    parser.add_argument("--no-notify", action="store_true", help="Niente Telegram")
    parser.add_argument("--add", action="store_true", help="Aggiungi ticker al portafoglio")
    parser.add_argument("--list", action="store_true", help="Lista portafoglio")
    args = parser.parse_args(argv)

    if args.list:
        print(json.dumps(list_portfolio(), indent=2, ensure_ascii=False))
        return 0

    if args.scan:
        out = scan_portfolio(notify=not args.no_notify)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0

    if not args.ticker:
        parser.print_help()
        return 1

    if args.add:
        add_ticker(args.ticker, sector=args.sector or "GENERICO")

    analysis = analyze_auto(args.ticker, sector=args.sector)
    prev = latest_score(analysis["ticker"])
    old_score = float(prev["score"]) if prev and prev.get("score") is not None else None
    save_score(analysis["ticker"], analysis)
    if not args.no_notify:
        maybe_notify(
            analysis["ticker"],
            old_score=old_score,
            new_score=analysis["score"],
            verdict=analysis["verdict"],
            buy_target=analysis.get("buy_target_price"),
        )
    print(analysis["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
