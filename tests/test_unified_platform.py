"""Tests for unified platform modules."""

from __future__ import annotations

from finance_alert.regulatory.hub import detect_region, regulatory_check


def test_detect_region_us():
    assert detect_region("NVDA") == "US"
    assert detect_region("AAPL") == "US"


def test_detect_region_suffixes():
    assert detect_region("SAP.DE") == "DE"
    assert detect_region("MC.PA") == "FR"
    assert detect_region("RACE.MI") == "IT"
    assert detect_region("7203.T") == "JP"
    assert detect_region("VOD.L") == "UK"


def test_regulatory_check_us_minimal():
    profile = regulatory_check("NVDA", company_name="NVIDIA")
    assert profile.ticker == "NVDA"
    assert profile.region == "US"
    assert isinstance(profile.flags, list)


def test_quant_score_bounds():
    from finance_alert.analysis.quantitative import quant_score_from_metrics

    assert 0 <= quant_score_from_metrics(20, 20, -10) <= 10
    assert quant_score_from_metrics(None, None, None) == 5.0


def test_unified_config_loads():
    from finance_alert.unified_config import load_unified_config

    cfg = load_unified_config()
    assert cfg.rules.min_unified_score >= 0
