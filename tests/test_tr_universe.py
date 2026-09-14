from __future__ import annotations

from finance_alert.sources import wire_rss
from finance_alert.tr_universe import NameMatcher, TrInstrument, save_universe
from finance_alert.config import Ticker


def test_name_matcher_finds_company():
    instruments = [
        TrInstrument(isin="US0378331005", name="Apple", ticker="AAPL"),
        TrInstrument(isin="US0231351067", name="Amazon.com", ticker="AMZN"),
        TrInstrument(isin="US88160R1014", name="Tesla", ticker="TSLA"),
    ]
    matcher = NameMatcher(instruments, min_name_len=4)
    hit = matcher.match("Apple raises guidance after strong iPhone sales")
    assert hit is not None and hit.ticker == "AAPL"
    hit2 = matcher.match("Something about TSLA deliveries")
    assert hit2 is not None and hit2.ticker == "TSLA"


def test_wire_uses_tr_universe(monkeypatch, tmp_path):
    instruments = [
        TrInstrument(isin="US0378331005", name="Apple Inc", ticker="AAPL"),
    ]
    path = tmp_path / "tr.json"
    save_universe(instruments, path)

    monkeypatch.setattr(
        "finance_alert.tr_universe.DEFAULT_PATH",
        path,
    )
    monkeypatch.setattr(
        "finance_alert.tr_universe._matcher_cache",
        None,
    )

    def fake_load(publisher, url, referer):
        return [
            {
                "headline": "Apple Inc announces major product launch",
                "url": "https://example.com/a",
                "published": None,
            }
        ]

    monkeypatch.setattr(wire_rss, "_load_feed", fake_load)
    items = wire_rss.fetch_news([], use_tr_universe=True)
    assert len(items) == 1
    assert items[0].ticker == "AAPL"
    assert items[0].source == "wire_rss"


def test_wire_watchlist_still_works(monkeypatch):
    def fake_load(publisher, url, referer):
        return [
            {
                "headline": "NVDA beats estimates and raises guidance",
                "url": "https://example.com/n",
                "published": None,
            }
        ]

    monkeypatch.setattr(wire_rss, "_load_feed", fake_load)
    monkeypatch.setattr(wire_rss, "_match_tr_universe", lambda h: None)
    items = wire_rss.fetch_news([Ticker(ticker="NVDA", name="NVIDIA")], use_tr_universe=False)
    assert len(items) == 1
    assert items[0].ticker == "NVDA"
