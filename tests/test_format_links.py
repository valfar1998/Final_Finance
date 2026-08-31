from finance_alert.format import format_alerts
from finance_alert.models import Alert


def test_format_includes_tradingview_and_source_links():
    alert = Alert(
        key="news|NVDA|x",
        tipo="news",
        ticker="NVDA",
        titolo="NVDA — test",
        body="Headline test",
        url="https://example.com/pr",
        setup_score=7,
        verdict="INTERESSANTE",
        tags=["LLM Unverified"],
    )
    text = format_alerts([alert])
    assert "tradingview.com/chart/?symbol=NVDA" in text
    assert "https://example.com/pr" in text
    assert "[LLM Unverified]" in text
