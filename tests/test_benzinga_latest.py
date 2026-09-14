from finance_alert.sources import benzinga


def test_benzinga_latest_expands_tickers(monkeypatch):
    monkeypatch.setattr(benzinga, "available", lambda: True)

    def fake_get_json(url, params=None, headers=None, timeout=20.0, retries=2):
        return [
            {
                "title": "Wedbush raises SentinelOne target",
                "url": "https://example.com/s",
                "created": "2026-09-11T12:00:00Z",
                "stocks": [{"name": "S"}, {"name": "CRWD"}],
                "author": "Desk",
            }
        ]

    monkeypatch.setattr(benzinga, "get_json", fake_get_json)
    items = benzinga.fetch_latest_news(page_size=10)
    ticks = {i.ticker for i in items}
    assert ticks == {"S", "CRWD"}
    assert all(i.source == "benzinga" for i in items)
