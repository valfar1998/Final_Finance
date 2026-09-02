from datetime import datetime, timezone
from unittest.mock import patch

from finance_alert.models import Alert, EarningsEvent, Quote
from finance_alert.rules import _apply_earnings_risk, _earnings_within_hours
from finance_alert.stats_util import robust_average


def test_robust_average_trims_outlier():
    values = [100.0, 105.0, 98.0, 102.0, 5000.0]
    avg = robust_average(values, trim_pct=0.1)
    assert avg < 200.0
    assert avg > 95.0


def test_earnings_within_hours_detects_imminent():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    earnings = [
        EarningsEvent(ticker="NVDA", date="2026-09-03", hour="amc"),
    ]
    assert _earnings_within_hours("NVDA", earnings, now, hours=72) is True
    assert _earnings_within_hours("AAPL", earnings, now, hours=72) is False


def test_earnings_risk_blocks_alert():
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    alert = Alert(
        key="news|NVDA|x",
        tipo="news",
        ticker="NVDA",
        titolo="test",
        body="body",
        setup_score=8,
    )
    earnings = [EarningsEvent(ticker="NVDA", date="2026-09-02", hour="amc")]
    assert _apply_earnings_risk(alert, earnings, now, enabled=True) is None
    assert "RISK: Earnings in < 72h" in alert.tags


def test_earnings_gate_disabled_passes():
    from finance_alert.rules import _apply_earnings_risk

    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    alert = Alert(
        key="news|NVDA|x",
        tipo="news",
        ticker="NVDA",
        titolo="test",
        body="body",
        setup_score=8,
    )
    earnings = [EarningsEvent(ticker="NVDA", date="2026-09-02", hour="amc")]
    kept = _apply_earnings_risk(alert, earnings, now, enabled=False)
    assert kept is alert
    assert kept.setup_score == 8


def test_skips_halted_extended_hours():
    from finance_alert.config import load_config
    from finance_alert.rules import build_alerts
    from tests.test_rules import _quote

    cfg = load_config()
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    quotes = {
        "NVDA": _quote(
            ticker="NVDA",
            price=171.5,
            previous_close=166,
            change_pct=3.5,
            session="pre",
            halted=True,
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
    assert all(a.tipo != "extended_hours" or a.ticker != "NVDA" for a in alerts)


def test_performance_tracker_records_sent(tmp_path, monkeypatch):
    from finance_alert import performance_tracker as pt

    store = tmp_path / "performance_tracker.json"
    monkeypatch.setattr(pt, "TRACKER_PATH", store)
    alert = Alert(
        key="news|NVDA|abc",
        tipo="news",
        ticker="NVDA",
        titolo="t",
        body="b",
        entry_price=100.0,
        target_price=103.0,
        stop_price=98.0,
        setup_score=7,
    )
    pt.record_sent([alert], {"NVDA": Quote(ticker="NVDA", price=100.0)})
    data = pt._load()
    assert len(data["records"]) == 1
    assert data["records"][0]["ticker"] == "NVDA"
