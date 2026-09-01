"""Livelli tecnici leggeri (resistenza da massimi recenti, ATR)."""

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


def compute_atr(ticker: str, period: int = 14) -> float | None:
    """ATR semplice su barre giornaliere Yahoo (fallback se indisponibile)."""
    ohlc = yahoo.fetch_daily_ohlc(ticker, days=max(period + 5, 25))
    if len(ohlc) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(ohlc)):
        high, low, prev_close = ohlc[i][1], ohlc[i][2], ohlc[i - 1][3]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if len(trs) < period:
        return None
    window = trs[-period:]
    return sum(window) / len(window)
