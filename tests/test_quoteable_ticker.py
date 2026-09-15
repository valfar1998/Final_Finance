from __future__ import annotations

from unittest.mock import patch

from finance_alert.models import is_quoteable_ticker
from finance_alert.sources import fmp
from finance_alert.tr_universe import NameMatcher, TrInstrument


def test_is_quoteable_accepts_common_equity():
    assert is_quoteable_ticker("AAPL")
    assert is_quoteable_ticker("BRK.B")
    assert is_quoteable_ticker("005930.KS")
    assert is_quoteable_ticker("bf-b")


def test_is_quoteable_rejects_openfigi_junk():
    assert not is_quoteable_ticker("MSTR 12 PERP A")
    assert not is_quoteable_ticker("BEPUCN 4.625 PERP")
    assert not is_quoteable_ticker("DNMR*")
    assert not is_quoteable_ticker("FOO,BAR")
    assert not is_quoteable_ticker("")


def test_fmp_fetch_quotes_skips_spaced_tickers():
    with patch.object(fmp, "available", return_value=True), patch.object(
        fmp, "get_json"
    ) as mock_json:
        mock_json.return_value = [
            {"symbol": "AAPL", "price": 100, "previousClose": 99, "changesPercentage": 1.0}
        ]
        out = fmp.fetch_quotes(["AAPL", "MSTR 12 PERP A", "BEPUCN 4.625 PERP"])
    assert "AAPL" in out
    url = mock_json.call_args.args[0]
    assert " " not in url
    assert "MSTR" not in url
    assert "AAPL" in url


def test_name_matcher_skips_perp_ticker_index():
    instruments = [
        TrInstrument(isin="USX", name="MicroStrategy Perp Junk", ticker="MSTR 12 PERP A"),
        TrInstrument(isin="US0378331005", name="Apple", ticker="AAPL"),
    ]
    matcher = NameMatcher(instruments, min_name_len=4)
    assert "MSTR 12 PERP A" not in matcher._by_ticker
    assert matcher.match("Something about MSTR 12 PERP A today") is None
    assert matcher.match("Apple raises guidance").ticker == "AAPL"
