"""Fundamental analysis via stock_analysis (Yahoo API + scoring engine)."""

from __future__ import annotations

import re
from typing import Any

from finance_alert.analysis.bridge import ensure_stock_analysis


NOT_AVAILABLE = "non disponibile"


def _guess_sector(ticker: str, info: dict[str, Any]) -> str:
    sector = str(info.get("sector") or info.get("industry") or "").upper()
    mapping = {
        "REAL ESTATE": "REIT",
        "FINANCIAL": "FINANCIALS",
        "TECHNOLOGY": "TECH",
        "HEALTH": "HEALTHCARE",
        "ENERGY": "ENERGY",
        "UTILITIES": "ENERGY",
        "CONSUMER": "CONSUMER",
        "INDUSTRIAL": "INDUSTRIAL",
        "COMMUNICATION": "COMMUNICATION",
    }
    for key, val in mapping.items():
        if key in sector:
            return val
    if ticker.endswith((".PA", ".DE", ".MI", ".L")):
        return "GENERICO"
    return "GENERICO"


def _parse_buy_price(target_txt: str) -> float | None:
    m = re.search(r"\$(\d+(?:\.\d+)?)", target_txt or "")
    if m:
        return float(m.group(1))
    return None


def _sanitized_buy_price(metrics: dict, sector: str, score: float, reliable: bool) -> float | None:
    """Evita target assurdi quando il BVPS cap domina su titoli growth."""
    from scoring_engine import buy_target  # type: ignore

    price = metrics.get("price")
    if not price or not reliable:
        return None
    txt = buy_target(metrics, sector, score, reliable)
    parsed = _parse_buy_price(txt)
    if parsed is None:
        return None
    # Se il minimo è >50% sotto il prezzo, usa solo sconto fondamentale + target analisti
    if parsed < price * 0.5:
        if score >= 80:
            fallback = price * 0.95
        elif score >= 60:
            fallback = price * 0.90
        elif score >= 40:
            fallback = price * 0.85
        else:
            fallback = price * 0.75
        target = metrics.get("target")
        n = metrics.get("n_analysts") or 0
        if n >= 5 and target:
            fallback = min(fallback, target * 0.92)
        return round(fallback, 2)
    return parsed


def analyze_fundamental(ticker: str, *, sector: str | None = None) -> dict[str, Any]:
    """Run stock_analysis scoring with Yahoo-only data (no HTML upload)."""
    ensure_stock_analysis()
    from yahoo_api import fetch_yahoo_metrics  # type: ignore
    from scoring_engine import buy_target, run_analysis  # type: ignore

    metrics = fetch_yahoo_metrics(ticker)
    sec = sector or _guess_sector(ticker, metrics)
    result = run_analysis(
        investing=NOT_AVAILABLE,
        tikr=NOT_AVAILABLE,
        sector=sec,
        yahoo_metrics=metrics,
    )
    score = float(result.get("score") or 0)
    reliable = bool(result.get("reliable"))
    target_txt = buy_target(metrics, sec, score, reliable)
    buy_price = _sanitized_buy_price(metrics, sec, score, reliable)
    return {
        "ticker": ticker.upper(),
        "sector": sec,
        "score": score,
        "reliable": reliable,
        "verdict": str(result.get("verdict") or ""),
        "buy_target_text": target_txt,
        "buy_target_price": buy_price,
        "price": metrics.get("price"),
        "pe": metrics.get("pe"),
        "rev_growth": metrics.get("rev_growth"),
        "smart_money_bonus": result.get("smart_money_bonus"),
        "metrics": metrics,
        "report": result.get("report") or "",
    }
