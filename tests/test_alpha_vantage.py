"""Unit tests for Alpha Vantage helpers (no live API calls)."""

from __future__ import annotations

from finance_alert.sources import alpha_vantage


def test_parse_av_time_news_sentiment_format():
    when = alpha_vantage._parse_av_time("20240917T163000")
    assert when is not None
    assert when.year == 2024 and when.month == 9 and when.day == 17
    assert when.hour == 16 and when.minute == 30


def test_available_reads_env(monkeypatch):
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    assert alpha_vantage.available() is False
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")
    assert alpha_vantage.available() is True


def test_fetch_quote_parses_global_quote(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")

    def fake_query(params):
        assert params["function"] == "GLOBAL_QUOTE"
        assert params["symbol"] == "IBM"
        return {
            "Global Quote": {
                "01. symbol": "IBM",
                "05. price": "150.25",
                "08. previous close": "148.00",
                "10. change percent": "1.5200%",
                "06. volume": "1000",
            }
        }

    monkeypatch.setattr(alpha_vantage, "_query", fake_query)
    q = alpha_vantage.fetch_quote("IBM")
    assert q is not None
    assert q.price == 150.25
    assert q.previous_close == 148.0
    assert q.change_pct == 1.52
    assert q.source == "alpha_vantage"


def test_fetch_quotes_caps_per_run(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")
    calls: list[str] = []

    def fake_quote(ticker: str):
        calls.append(ticker)
        return None

    monkeypatch.setattr(alpha_vantage, "fetch_quote", fake_quote)
    tickers = [f"T{i}" for i in range(20)]
    alpha_vantage.fetch_quotes(tickers)
    assert len(calls) == alpha_vantage._MAX_QUOTE_PER_RUN
