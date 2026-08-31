"""Livelli tecnici leggeri (resistenza da massimi recenti)."""

from __future__ import annotations

from finance_alert.sources import yahoo


def nearest_resistance(ticker: str, price: float | None) -> float | None:
    if price is None or price <= 0:
        return None
    highs = yahoo.fetch_recent_daily_highs(ticker, days=20)
    above = [h for h in highs if h > price * 1.002]
    if not above:
        return None
    return min(above)


def fmt_resistance(level: float | None) -> str:
    return "n.d." if level is None else f"${level:.2f}"
