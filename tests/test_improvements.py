from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from finance_alert.config import SwingRules
from finance_alert.dedupe import SentRecord, is_semantic_duplicate
from finance_alert.models import Alert
from finance_alert.swing import build_swing_plan
from finance_alert.technical import compute_atr
from tests.test_rules import _quote


def test_dedupe_respects_time_window():
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    alert = Alert(
        key="news|NVDA|new",
        tipo="news",
        ticker="NVDA",
        titolo="NVDA — news",
        body="NVIDIA raised guidance after beat estimates\nCNBC",
    )
    old = SentRecord(
        key="news|NVDA|old",
        ts=now - timedelta(hours=3),
        ticker="NVDA",
        headline="NVIDIA raised guidance after beating estimates",
        tipo="news",
    )
    assert not is_semantic_duplicate(
        alert, [old], threshold=0.55, window_hours=2.0, llm_equiv=False, now=now
    )


def test_dedupe_blocks_within_window():
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    alert = Alert(
        key="news|NVDA|new",
        tipo="news",
        ticker="NVDA",
        titolo="NVDA — news",
        body="NVIDIA raised guidance after beat estimates\nCNBC",
    )
    recent = SentRecord(
        key="news|NVDA|old",
        ts=now - timedelta(minutes=45),
        ticker="NVDA",
        headline="NVIDIA raised guidance after beating estimates",
        tipo="news",
    )
    assert is_semantic_duplicate(
        alert, [recent], threshold=0.55, window_hours=2.0, llm_equiv=False, now=now
    )


def test_swing_plan_uses_atr_when_available():
    swing = SwingRules(use_atr=True, atr_target_mult=1.5, atr_stop_mult=1.0)
    quote = _quote(ticker="MARA", price=20.0, previous_close=19.5)
    with patch("finance_alert.swing.compute_atr", return_value=2.0), patch(
        "finance_alert.swing.nearest_resistance", return_value=None
    ):
        plan = build_swing_plan(tipo="peer_lag", quote=quote, pct=0.5, swing=swing)
    assert plan is not None
    assert plan.target == 23.0
    assert plan.stop == 18.0
    assert "ATR" in plan.note


def test_swing_plan_caps_target_at_resistance():
    swing = SwingRules(use_atr=True, atr_target_mult=1.5, atr_stop_mult=1.0)
    quote = _quote(ticker="NVDA", price=100.0, previous_close=99.0)
    with patch("finance_alert.swing.compute_atr", return_value=4.0), patch(
        "finance_alert.swing.nearest_resistance", return_value=104.0
    ):
        plan = build_swing_plan(tipo="peer_lag", quote=quote, pct=0.5, swing=swing)
    assert plan is not None
    assert plan.target == 104.0
    assert "resistenza" in plan.note.lower()


def test_llm_fallback_approves_primary_catalyst_only():
    from finance_alert.models import NewsItem
    from finance_alert.news_llm import verify_news_catalyst

    primary = NewsItem(
        ticker="NVDA",
        headline="NVIDIA raised guidance after beat estimates",
        url="https://example.com",
        source="test",
        publisher="CNBC",
        score=10,
    )
    generic = NewsItem(
        ticker="NVDA",
        headline="NVIDIA shares move on market sentiment",
        url="https://example.com/2",
        source="test",
        publisher="CNBC",
        score=10,
    )
    with patch("finance_alert.news_llm._provider", return_value="groq"), patch(
        "finance_alert.news_llm._call_groq", return_value=None
    ):
        ok = verify_news_catalyst(primary)
        bad = verify_news_catalyst(generic)
    assert ok.approved is True
    assert ok.score == 6
    assert ok.unverified is True
    assert bad.approved is False
    assert bad.score <= 5


def test_gap_exceeds_atr_target_skips_extended_hours():
    from finance_alert.rules import _gap_exceeds_atr_target

    quote = _quote(ticker="TSLA", price=110.0, previous_close=100.0, session="pre")
    swing = SwingRules(use_atr=True, atr_target_mult=1.5)
    with patch("finance_alert.rules.compute_atr", return_value=5.0):
        assert _gap_exceeds_atr_target(quote, swing) is True
    with patch("finance_alert.rules.compute_atr", return_value=10.0):
        assert _gap_exceeds_atr_target(quote, swing) is False


def test_compute_atr_from_ohlc():
    rows = []
    price = 100.0
    for _ in range(20):
        rows.append((price, price + 2, price - 1, price + 0.5))
        price += 0.5
    with patch("finance_alert.technical.yahoo.fetch_daily_ohlc", return_value=rows):
        atr = compute_atr("TEST", period=14)
    assert atr is not None
    assert 2.5 <= atr <= 3.5
