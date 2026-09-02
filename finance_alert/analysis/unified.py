"""Unified score: fundamental + quantitative + regulatory + catalyst."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finance_alert.analysis.fundamental import analyze_fundamental
from finance_alert.analysis.quantitative import analyze_quantitative
from finance_alert.regulatory.hub import regulatory_check


@dataclass
class UnifiedAnalysis:
    ticker: str
    fundamental_score: float = 0.0  # 0-100
    quant_score: float = 0.0  # 0-10
    catalyst_score: float = 0.0  # 0-10
    regulatory_penalty: float = 0.0
    unified_score: float = 0.0  # 0-10
    verdict: str = ""
    buy_target_price: float | None = None
    buy_target_text: str = ""
    recommended_entry: float | None = None
    flags: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def summary_lines(self) -> list[str]:
        lines = [
            f"📊 Score unificato: {self.unified_score:.1f}/10",
            f"   Fondamentale: {self.fundamental_score:.0f}/100 | Quant: {self.quant_score:.1f}/10",
            f"   Verdetto: {self.verdict}",
        ]
        if self.buy_target_price:
            lines.append(f"   🎯 Prezzo acquisto consigliato: ${self.buy_target_price:.2f}")
        elif self.buy_target_text:
            lines.append(f"   🎯 Target: {self.buy_target_text[:80]}")
        if self.recommended_entry:
            lines.append(f"   ⚡ Entry swing suggerita: ${self.recommended_entry:.2f}")
        for flag in self.flags[:3]:
            lines.append(f"   ⚠ {flag}")
        return lines


def compute_unified(
    ticker: str,
    *,
    catalyst_score: float = 0.0,
    swing_entry: float | None = None,
    sector: str | None = None,
    skip_regulatory: bool = False,
) -> UnifiedAnalysis:
    fund = analyze_fundamental(ticker, sector=sector)
    quant = analyze_quantitative(ticker)
    reg = None if skip_regulatory else regulatory_check(ticker, company_name=str(fund.get("metrics", {}).get("name") or ticker))

    f_score = float(fund["score"])
    q_score = float(quant["quant_score"])
    reg_pen = float(reg.score_penalty) if reg else 0.0

    # Pesi: 50% fondamentale, 25% quant, 25% catalizzatore (se presente)
    if catalyst_score > 0:
        unified = (
            0.50 * (f_score / 10.0)
            + 0.25 * q_score
            + 0.25 * catalyst_score
            - reg_pen
        )
    else:
        unified = 0.55 * (f_score / 10.0) + 0.45 * q_score - reg_pen

    unified = max(0.0, min(10.0, unified))

    buy_price = fund.get("buy_target_price")
    entry = swing_entry or buy_price

    out = UnifiedAnalysis(
        ticker=ticker.upper(),
        fundamental_score=f_score,
        quant_score=q_score,
        catalyst_score=catalyst_score,
        regulatory_penalty=reg_pen,
        unified_score=unified,
        verdict=str(fund.get("verdict") or ""),
        buy_target_price=buy_price,
        buy_target_text=str(fund.get("buy_target_text") or ""),
        recommended_entry=entry,
        flags=list(reg.flags) if reg else [],
        details={"fundamental": fund, "quantitative": quant, "regulatory": reg.__dict__ if reg else {}},
    )
    return out
