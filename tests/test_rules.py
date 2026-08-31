from datetime import datetime, timezone

from finance_alert.config import load_config
from finance_alert.dedupe import headline_similarity, is_semantic_duplicate, record_from_alert, SentRecord
from finance_alert.models import Alert, EarningsEvent, Filing, NewsItem, Quote
from finance_alert.rules import build_alerts
from finance_alert.swing import build_swing_plan


def _quote(**kwargs) -> Quote:
    base = dict(source="test", rvol=3.5, dollar_volume=400_000.0, price=100.0)
    base.update(kwargs)
    if base.get("dollar_volume") and base.get("price") and base.get("volume") is None:
        base["volume"] = float(base["dollar_volume"]) / float(base["price"])
    return Quote(**base)


def test_early_mode_keeps_catalysts_drops_late_spike():
    cfg = load_config()
    assert cfg.rules.only_upside is True
    assert cfg.rules.swing.min_setup_score == 6
    assert cfg.rules.filing_items_only == ["2.02", "1.01"]
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": _quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166.0,
            change_pct=3.5,
            session="regular",
        ),
        "AMD": _quote(ticker="AMD", price=100, previous_close=100.5, change_pct=-0.5),
        "AVGO": _quote(ticker="AVGO", price=360, previous_close=358, change_pct=0.5),
        "SMCI": _quote(ticker="SMCI", price=38, previous_close=38, change_pct=0.0),
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


def test_extended_hours_requires_rvol():
    cfg = load_config()
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": _quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166,
            change_pct=3.5,
            session="pre",
        ),
        "AMD": _quote(
            ticker="AMD",
            price=100,
            previous_close=100.2,
            change_pct=-0.2,
            session="pre",
        ),
        "AVGO": _quote(
            ticker="AVGO",
            price=360,
            previous_close=355,
            change_pct=1.4,
            session="pre",
        ),
        "SMCI": _quote(
            ticker="SMCI",
            price=38,
            previous_close=38,
            change_pct=0.1,
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
    ext = next(a for a in alerts if a.tipo == "extended_hours")
    assert "RVOL" in ext.body


def test_skips_low_rvol_extended_hours():
    cfg = load_config()
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": Quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166,
            change_pct=3.5,
            source="test",
            session="pre",
            rvol=1.2,
        ),
        "AMD": _quote(ticker="AMD", price=100, previous_close=100.2, change_pct=-0.2, session="pre"),
        "AVGO": _quote(ticker="AVGO", price=360, previous_close=355, change_pct=1.4, session="pre"),
        "SMCI": _quote(ticker="SMCI", price=38, previous_close=38, change_pct=0.1, session="pre"),
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
    assert all(a.tipo != "extended_hours" for a in alerts)


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
        quotes={"NVDA": _quote(ticker="NVDA", price=178, previous_close=170)},
        earnings=[],
        news=[noise, useful],
        filings=[],
        momentum={},
    )
    news_alerts = [a for a in alerts if a.tipo == "news"]
    assert len(news_alerts) == 1
    assert "guidance" in news_alerts[0].body.lower() or "raised" in news_alerts[0].body.lower()


def test_swing_plan_includes_entry_target_stop():
    cfg = load_config()
    quote = _quote(ticker="AMD", price=100.0, previous_close=99.0)
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


def test_semantic_dedupe_blocks_similar_headline():
    alert = Alert(
        key="news|NVDA|abc",
        tipo="news",
        ticker="NVDA",
        titolo="NVDA — news",
        body="NVIDIA raised guidance after beat estimates\nCNBC",
    )
    prior = SentRecord(
        key="news|NVDA|old",
        ts=datetime.now(timezone.utc),
        ticker="NVDA",
        headline="NVIDIA raised guidance after beating estimates",
        tipo="news",
    )
    assert headline_similarity(alert.body.split("\n")[0], prior.headline) >= 0.5
    assert is_semantic_duplicate(alert, [prior], threshold=0.55)


def test_skips_low_dollar_volume_extended_hours():
    cfg = load_config()
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": Quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166,
            change_pct=3.5,
            source="test",
            session="pre",
            rvol=4.0,
            dollar_volume=50_000,
        ),
        "AMD": _quote(ticker="AMD", price=100, previous_close=100.2, change_pct=-0.2, session="pre"),
        "AVGO": _quote(ticker="AVGO", price=360, previous_close=355, change_pct=1.4, session="pre"),
        "SMCI": _quote(ticker="SMCI", price=38, previous_close=38, change_pct=0.1, session="pre"),
    }
    alerts = build_alerts(cfg=cfg, now=now, quotes=quotes, earnings=[], news=[], filings=[], momentum={})
    assert all(a.tipo != "extended_hours" for a in alerts)


def test_macro_stress_raises_min_setup_score():
    from finance_alert.macro import effective_min_setup_score

    cfg = load_config()
    normal = effective_min_setup_score(cfg.rules.macro, {"SPY": -0.5, "QQQ": -0.3})
    stressed = effective_min_setup_score(cfg.rules.macro, {"SPY": -2.0, "QQQ": -1.8})
    assert normal == cfg.rules.macro.normal_min_setup_score
    assert stressed == cfg.rules.macro.stressed_min_setup_score


def test_filing_filters_routine_items():
    cfg = load_config()
    now = datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc)
    filings = [
        Filing(ticker="NVDA", form="8-K", accession="x1", filed="2026-08-27", items="5.02"),
        Filing(ticker="NVDA", form="8-K", accession="x2", filed="2026-08-27", items="1.01"),
    ]
    alerts = build_alerts(
        cfg=cfg,
        now=now,
        quotes={"NVDA": _quote(ticker="NVDA", price=170, previous_close=166)},
        earnings=[],
        news=[],
        filings=filings,
        momentum={},
    )
    filing_alerts = [a for a in alerts if a.tipo == "filing_8k"]
    assert len(filing_alerts) == 1
    assert "1.01" in filing_alerts[0].body
