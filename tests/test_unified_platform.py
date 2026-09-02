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
    assert detect_region("005930.KS") == "KR"
    assert detect_region("035720.KQ") == "KR"
    assert detect_region("600519.SS") == "CN"
    assert detect_region("300750.SZ") == "CN"
    assert detect_region("0700.HK") == "HK"


def test_eodhd_symbol_mapping():
    from finance_alert.sources.eodhd import to_eodhd_symbol

    assert to_eodhd_symbol("AAPL") == "AAPL.US"
    assert to_eodhd_symbol("600519.SS") == "600519.SH"
    assert to_eodhd_symbol("005930.KS") == "005930.KS"
    assert to_eodhd_symbol("0700.HK") == "0700.HK"


def test_asia_status_without_libs():
    from finance_alert.markets.asia import status

    st = status()
    assert "akshare" in st
    assert "pykrx" in st
    assert "finance_data_reader" in st
    assert "tushare" in st


def test_opendart_normalize_and_missing_key():
    from finance_alert.regulatory.opendart import _normalize_kr_ticker, filings_for_ticker

    assert _normalize_kr_ticker("005930.KS") == "005930"
    assert _normalize_kr_ticker("660.KS") == "000660"
    result = filings_for_ticker("005930.KS")
    assert "OPEN_DART_API_KEY" in result.error


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
