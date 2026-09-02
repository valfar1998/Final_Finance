"""Load unified platform configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from finance_alert.env import ROOT

UNIFIED_PATH = ROOT / "config" / "unified.yaml"


@dataclass
class UnifiedRules:
    enabled: bool = True
    min_fundamental_score: float = 40.0  # 0-100 quality gate
    min_unified_score: float = 5.0  # 0-10 to send enriched alert
    enrich_telegram: bool = True
    quality_gate_block: bool = False  # if True, silences alerts below min score
    include_regulatory: bool = True
    screener_min_score: float = 7.0  # unified score to enter dynamic watchlist
    screener_tickers: list[str] = field(default_factory=list)


@dataclass
class UnifiedConfig:
    rules: UnifiedRules


def load_unified_config(path: Path | None = None) -> UnifiedConfig:
    target = path or UNIFIED_PATH
    data: dict[str, Any] = {}
    if target.is_file():
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            data = loaded
    raw = data.get("unified") or data.get("rules") or data
    if not isinstance(raw, dict):
        raw = {}
    screener = raw.get("screener_tickers") or []
    rules = UnifiedRules(
        enabled=bool(raw.get("enabled", True)),
        min_fundamental_score=float(
            os.getenv("UNIFIED_MIN_FUNDAMENTAL") or raw.get("min_fundamental_score") or 40
        ),
        min_unified_score=float(os.getenv("UNIFIED_MIN_SCORE") or raw.get("min_unified_score") or 5),
        enrich_telegram=bool(raw.get("enrich_telegram", True)),
        quality_gate_block=bool(raw.get("quality_gate_block", False)),
        include_regulatory=bool(raw.get("include_regulatory", True)),
        screener_min_score=float(raw.get("screener_min_score") or 7.0),
        screener_tickers=[str(t).upper() for t in screener if str(t).strip()],
    )
    return UnifiedConfig(rules=rules)
