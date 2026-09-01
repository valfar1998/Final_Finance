"""Piano operativo swing 5-7 giorni (target/stop indicativi, non consiglio finanziario)."""

from __future__ import annotations

from dataclasses import dataclass

from finance_alert.config import SwingRules
from finance_alert.models import Quote
from finance_alert.technical import compute_atr, nearest_resistance


@dataclass
class SwingPlan:
    score: int
    verdict: str
    entry_lo: float | None
    entry_hi: float | None
    target: float | None
    stop: float | None
    horizon_days: int
    note: str = ""

    def body_lines(self) -> list[str]:
        lines = [f"Setup swing: {self.score}/10 · {self.verdict}"]
        if self.entry_lo is not None and self.entry_hi is not None:
            lines.append(f"Ingresso ideale: ${self.entry_lo:.2f}–${self.entry_hi:.2f}")
        if self.target is not None:
            lines.append(f"Target {self.horizon_days}g: ${self.target:.2f}")
        if self.stop is not None:
            lines.append(f"Stop: ${self.stop:.2f}")
        if self.note:
            lines.append(self.note)
        return lines


def _clamp_score(value: int) -> int:
    return max(1, min(10, value))


def build_swing_plan(
    *,
    tipo: str,
    quote: Quote | None,
    pct: float | None,
    swing: SwingRules,
    news_score: int = 0,
    upside: bool = True,
) -> SwingPlan | None:
    if quote is None or quote.price is None or quote.price <= 0:
        return None

    price = float(quote.price)
    prev = float(quote.previous_close or price)
    move = pct if pct is not None else quote.pct_from_close() or 0.0
    horizon = swing.horizon_days

    atr = None
    if swing.use_atr and quote.ticker:
        atr = compute_atr(quote.ticker, period=swing.atr_period)
    if atr and atr > 0:
        atr_upside = swing.atr_target_mult * atr
        target = price + atr_upside
        resist = nearest_resistance(quote.ticker, price) if quote.ticker else None
        if resist is not None:
            target = min(target, resist)
            if target <= price:
                return None
            if target < price + atr_upside:
                target_note = (
                    f"ATR {atr:.2f} → cap resistenza ${resist:.2f} "
                    f"(target {swing.atr_target_mult:g}×, stop {swing.atr_stop_mult:g}×)"
                )
            else:
                target_note = f"ATR {atr:.2f} → target {swing.atr_target_mult:g}×, stop {swing.atr_stop_mult:g}×"
        else:
            target_note = f"ATR {atr:.2f} → target {swing.atr_target_mult:g}×, stop {swing.atr_stop_mult:g}×"
        stop = price - swing.atr_stop_mult * atr
    else:
        target = price * (1 + swing.target_pct / 100.0)
        stop = price * (1 - swing.stop_pct / 100.0)
        target_note = f"obiettivo +{swing.target_pct:g}% (non garantito)"

    base = {
        "earnings_surprise": 8,
        "filing_8k": 7,
        "peer_lag": 7,
        "extended_hours": 6,
        "news": 5,
        "earnings_soon": 4,
    }.get(tipo, 5)

    score = base
    if tipo == "news":
        score += min(news_score // 2, 3)
    if tipo == "extended_hours":
        if 1.5 <= abs(move) <= 3.5:
            score += 1
        elif abs(move) > 5:
            score -= 3
    if not upside:
        score -= 4

    verdict = "INTERESSANTE"
    note = f"Orizzonte ~{horizon} giorni · {target_note}."

    if abs(move) >= swing.chase_pct:
        entry_lo = prev * (1 + swing.pullback_from_close_pct / 100.0)
        entry_hi = prev * (1 + (swing.pullback_from_close_pct + 1.0) / 100.0)
        verdict = "ATTENDI pullback"
        note = (
            f"Già {move:+.1f}% — non inseguire. "
            f"Rientra solo se torna verso ${entry_lo:.2f}–${entry_hi:.2f}."
        )
        score -= 2
    elif abs(move) >= 2:
        entry_lo = price * 0.992
        entry_hi = price * 1.008
        verdict = "INTERESSANTE · ingresso rapido"
        note = "Movimento in corso: ingresso solo se accetti poco slippage."
        score -= 1
    else:
        entry_lo = price * 0.995
        entry_hi = price * 1.01

    if tipo == "earnings_soon":
        verdict = "SOLO WATCHLIST"
        note = "Utili in arrivo: alta volatilità. Non è un segnale di ingresso."
        entry_lo = None
        entry_hi = None
        target = None
        stop = None

    score = _clamp_score(score)
    return SwingPlan(
        score=score,
        verdict=verdict,
        entry_lo=entry_lo,
        entry_hi=entry_hi,
        target=target,
        stop=stop,
        horizon_days=horizon,
        note=note,
    )
