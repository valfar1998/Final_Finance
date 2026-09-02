"""Bridge to sibling projects stock_analysis and Finance-Analyzer."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORSI = ROOT.parent

# Percorsi in-repo (Final_Finance) con fallback ai sibling in corsi/
STOCK_ANALYSIS = ROOT / "stock_analysis"
if not STOCK_ANALYSIS.is_dir():
    STOCK_ANALYSIS = CORSI / "stock_analysis"

FIN_ANALYZER = ROOT / "finance_analyzer" / "backend"
if not FIN_ANALYZER.is_dir():
    FIN_ANALYZER = CORSI / "Finance-Analyzer-main" / "backend"


def ensure_stock_analysis() -> Path:
    if not STOCK_ANALYSIS.is_dir():
        raise RuntimeError(f"stock_analysis non trovato in {STOCK_ANALYSIS}")
    path = str(STOCK_ANALYSIS)
    if path not in sys.path:
        sys.path.insert(0, path)
    return STOCK_ANALYSIS


def ensure_fin_analyzer() -> Path:
    if not FIN_ANALYZER.is_dir():
        raise RuntimeError(f"Finance-Analyzer backend non trovato in {FIN_ANALYZER}")
    path = str(FIN_ANALYZER)
    if path not in sys.path:
        sys.path.insert(0, path)
    return FIN_ANALYZER
