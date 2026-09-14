from __future__ import annotations

from finance_alert.config import PremarketRules
from finance_alert.premarket_universe import discover_hot_symbols
from finance_alert.sources import polygon


def test_yahoo_screener_symbols_parses(monkeypatch):
    from finance_alert.sources import yahoo

    def fake_get_json(url, params=None, headers=None, timeout=20.0, retries=2):
        scr = (params or {}).get("scrIds")
        if scr == "day_gainers":
            return {
                "finance": {
                    "result": [
                        {
                            "quotes": [
                                {"symbol": "AAA"},
                                {"symbol": "BBB-W"},
                                {"symbol": "CCC"},
                            ]
                        }
                    ]
                }
            }
        return {"finance": {"result": [{"quotes": [{"symbol": "DDD"}]}]}}

    monkeypatch.setattr(yahoo, "get_json", fake_get_json)
    syms = yahoo.fetch_screener_symbols(["day_gainers", "most_actives"], count=10)
    assert syms == ["AAA", "CCC", "DDD"]


def test_polygon_prev_day_movers_filters(monkeypatch):
    monkeypatch.setattr(polygon, "available", lambda: True)

    def fake_get_json(url, params=None, headers=None, timeout=20.0, retries=2):
        return {
            "status": "OK",
            "results": [
                {"T": "HOT1", "o": 10.0, "c": 12.0, "v": 2_000_000},  # +20%
                {"T": "LOWV", "o": 10.0, "c": 12.0, "v": 100},  # vol basso
                {"T": "PENNY", "o": 0.5, "c": 0.8, "v": 5_000_000},  # prezzo basso
                {"T": "FLAT", "o": 10.0, "c": 10.2, "v": 2_000_000},  # +2%
                {"T": "ZVZZT", "o": 1.0, "c": 3.0, "v": 5_000_000},  # test symbol
                {"T": "HOT2", "o": 20.0, "c": 22.0, "v": 3_000_000},  # +10%
            ],
        }

    monkeypatch.setattr(polygon, "get_json", fake_get_json)
    syms = polygon.fetch_prev_day_movers(min_abs_pct=5.0, min_volume=1_000_000, limit=10)
    assert syms == ["HOT1", "HOT2"]


def test_discover_hot_symbols_merges(monkeypatch):
    monkeypatch.setattr(
        "finance_alert.premarket_universe.yahoo.fetch_screener_symbols",
        lambda *a, **k: ["AAA", "BBB"],
    )
    monkeypatch.setattr(polygon, "available", lambda: True)
    monkeypatch.setattr(
        "finance_alert.premarket_universe.polygon.fetch_prev_day_movers",
        lambda **k: ["BBB", "CCC", "DDD"],
    )
    rules = PremarketRules(enabled=True, max_extra=3)
    disc = discover_hot_symbols(rules)
    assert disc.merged == ["AAA", "BBB", "CCC"]


def test_resolve_scan_keeps_watchlist_then_extras(monkeypatch):
    from finance_alert.config import AppConfig, EdgarConfig, Rules, Ticker
    from finance_alert.unified_config import UnifiedConfig, UnifiedRules
    from finance_alert import watchlist_resolver as wr

    cfg = AppConfig(
        watchlist=[Ticker(ticker="NVDA"), Ticker(ticker="AAPL")],
        rules=Rules(premarket=PremarketRules(enabled=True, max_extra=5)),
        edgar=EdgarConfig(),
        clusters=[],
    )
    monkeypatch.setattr(wr, "load_unified_config", lambda: UnifiedConfig(rules=UnifiedRules(max_scan_symbols=4)))
    monkeypatch.setattr(
        wr,
        "discover_hot_symbols",
        lambda rules: type("D", (), {"merged": ["HOT1", "HOT2", "HOT3"]})(),
    )
    symbols, tickers = wr.resolve_scan_symbols(cfg)
    assert symbols[:2] == ["NVDA", "AAPL"]
    assert "HOT1" in symbols and "HOT2" in symbols
    assert len(symbols) == 4
    assert [t.ticker for t in tickers] == symbols
