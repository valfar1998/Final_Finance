"""Enrich FINANCE NOTIFY alerts with unified fundamental + quant analysis."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from finance_alert.analysis.unified import UnifiedAnalysis, compute_unified
from finance_alert.db.store import record_alert, save_score
from finance_alert.unified_config import UnifiedConfig, load_unified_config

if TYPE_CHECKING:
    from finance_alert.models import Alert

_CACHE: dict[str, UnifiedAnalysis] = {}


@lru_cache(maxsize=1)
def _cfg() -> UnifiedConfig:
    return load_unified_config()


def get_analysis(ticker: str, *, catalyst_score: float = 0.0, entry: float | None = None) -> UnifiedAnalysis:
    key = ticker.upper()
    if key in _CACHE:
        return _CACHE[key]
    cfg = _cfg()
    analysis = compute_unified(
        key,
        catalyst_score=catalyst_score,
        swing_entry=entry,
        skip_regulatory=not cfg.rules.include_regulatory,
    )
    _CACHE[key] = analysis
    save_score(key, {
        "fundamental_score": analysis.fundamental_score,
        "quant_score": analysis.quant_score,
        "unified_score": analysis.unified_score,
        "verdict": analysis.verdict,
        "buy_target_price": analysis.buy_target_price,
    })
    return analysis


def enrich_alert(alert: "Alert") -> UnifiedAnalysis | None:
    cfg = _cfg()
    if not cfg.rules.enabled:
        return None
    if alert.ticker in ("*", ""):
        return None
    catalyst = float(alert.setup_score or 0)
    analysis = get_analysis(alert.ticker, catalyst_score=catalyst, entry=alert.entry_price)
    return analysis


def passes_quality_gate(analysis: UnifiedAnalysis) -> bool:
    cfg = _cfg()
    if analysis.fundamental_score >= cfg.rules.min_fundamental_score:
        return True
    if analysis.unified_score >= cfg.rules.min_unified_score:
        return True
    return False


def filter_alerts(alerts: list["Alert"]) -> list["Alert"]:
    """Optional quality gate — drops low-fundamental alerts when enabled."""
    cfg = _cfg()
    if not cfg.rules.enabled or not cfg.rules.quality_gate_block:
        return alerts
    kept: list[Alert] = []
    for alert in alerts:
        analysis = enrich_alert(alert)
        if analysis is None or passes_quality_gate(analysis):
            kept.append(alert)
        else:
            record_alert(alert.key, alert.ticker, analysis.unified_score, sent=False)
    return kept


def build_context_block(analysis: UnifiedAnalysis) -> str:
    lines = analysis.summary_lines()
    reg = analysis.details.get("regulatory") or {}
    region = reg.get("region")
    if region:
        lines.append(f"   🌍 Regolatore: {region} | Penalty: -{analysis.regulatory_penalty:.1f}")
    return "\n".join(lines)
