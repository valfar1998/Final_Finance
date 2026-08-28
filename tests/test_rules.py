from datetime import datetime, timezone

from finance_alert.config import load_config
from finance_alert.models import EarningsEvent, Filing, NewsItem, Quote
from finance_alert.rules import build_alerts
from finance_alert.swing import build_swing_plan


def test_early_mode_keeps_catalysts_drops_late_spike():
    cfg = load_config()
    assert cfg.rules.only_upside is True
    assert cfg.rules.swing.min_setup_score == 6
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": Quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166.0,
            change_pct=3.5,
            source="test",
            session="regular",
        ),
        "AMD": Quote(ticker="AMD", price=100, previous_close=100.5, change_pct=-0.5, source="test"),
        "AVGO": Quote(ticker="AVGO", price=360, previous_close=358, change_pct=0.5, source="test"),
        "SMCI": Quote(ticker="SMCI", price=38, previous_close=38, change_pct=0.0, source="test"),
    }
    earnings = [
        EarningsEvent(
            ticker="NVDA",
            date="2026-08-26",
            hour="amc",
            eps_actual=0.75,
            eps_estimate=0.62,
            revenue_actual=30_000_000_000,
            revenue_estimate=28_000_000_000,
            source="test",
        )
    ]
    news = [
        NewsItem(
            ticker="NVDA",
            headline="NVIDIA raised guidance after beat estimates",
            url="https://example.com/nvda",
            published=now,
            source="finnhub",
            publisher="CNBC",
        )
    ]
    filings = [
        Filing(
            ticker="NVDA",
            form="8-K",
            accession="0001045810-26-000099",
            filed="2026-08-27",
            items="2.02",
            url="https://www.sec.gov/example",
        )
    ]
    alerts = build_alerts(
        cfg=cfg,
        now=now,
        quotes=quotes,
        earnings=earnings,
        news=news,
        filings=filings,
        momentum={"NVDA": 3.1},
    )
    tipi = {a.tipo for a in alerts}
    assert "earnings_surprise" in tipi
    assert "filing_8k" in tipi
    assert "news" in tipi
    assert "peer_lag" in tipi
    assert "price_spike" not in tipi
    assert "momentum" not in tipi
    for alert in alerts:
        assert alert.setup_score >= cfg.rules.swing.min_setup_score
        assert "Setup swing:" in alert.body


def test_extended_hours_upside_only():
    cfg = load_config()
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": Quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166,
            change_pct=3.5,
            source="yahoo_ext",
            session="pre",
        ),
        "AMD": Quote(
            ticker="AMD",
            price=100,
            previous_close=100.2,
            change_pct=-0.2,
            source="yahoo_ext",
            session="pre",
        ),
        "AVGO": Quote(
            ticker="AVGO",
            price=360,
            previous_close=355,
            change_pct=1.4,
            source="yahoo_ext",
            session="pre",
        ),
        "SMCI": Quote(
            ticker="SMCI",
            price=38,
            previous_close=38,
            change_pct=0.1,
            source="yahoo_ext",
            session="pre",
        ),
    }
    alerts = build_alerts(
        cfg=cfg,
        now=now,
        quotes=quotes,
        earnings=[],
        news=[],
        filings=[],
        momentum={},
    )
    tipi = {a.tipo for a in alerts}
    assert "extended_hours" in tipi
    assert "peer_lag" in tipi
    assert all(a.tipo != "price_spike" for a in alerts)
    ext = next(a for a in alerts if a.tipo == "extended_hours")
    assert "pre-market" in ext.titolo.lower() or "pre" in ext.titolo.lower()
    peer = next(a for a in alerts if a.tipo == "peer_lag")
    assert peer.ticker == "AMD"
    assert peer.setup_score >= cfg.rules.swing.min_setup_score


def test_skips_seeking_alpha_opinion_without_catalyst():
    cfg = load_config()
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    noise = NewsItem(
        ticker="NVDA",
        headline="Q2: Nvidia Isn't Microsoft, And 2026 Isn't 1999",
        url="https://example.com/sa",
        published=now,
        source="finnhub",
        publisher="SeekingAlpha",
    )
    useful = NewsItem(
        ticker="NVDA",
        headline="NVIDIA raised guidance after beating estimates",
        url="https://example.com/cnbc",
        published=now,
        source="finnhub",
        publisher="CNBC",
    )
    alerts = build_alerts(
        cfg=cfg,
        now=now,
        quotes={"NVDA": Quote(ticker="NVDA", price=178, previous_close=170, source="test")},
        earnings=[],
        news=[noise, useful],
        filings=[],
        momentum={},
    )
    news_alerts = [a for a in alerts if a.tipo == "news"]
    assert len(news_alerts) == 1
    assert "guidance" in news_alerts[0].body.lower() or "raised" in news_alerts[0].body.lower()
    assert "Ingresso ideale" in news_alerts[0].body


def test_swing_plan_includes_entry_target_stop():
    cfg = load_config()
    quote = Quote(ticker="AMD", price=100.0, previous_close=99.0, source="test")
    plan = build_swing_plan(
        tipo="peer_lag",
        quote=quote,
        pct=0.5,
        swing=cfg.rules.swing,
    )
    assert plan is not None
    assert plan.score >= 6
    assert plan.entry_lo is not None
    assert plan.target is not None
    assert plan.stop is not None
    assert "2.5" in plan.body_lines()[2] or plan.target > 100
