from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from finance_alert.aggregator import (
    fetch_earnings,
    fetch_filings,
    fetch_momentum,
    fetch_news,
    fetch_quotes,
    overlay_extended_hours,
    overlay_volume_stats,
    source_status,
)
from finance_alert.config import AppConfig, load_config
from finance_alert.dedupe import (
    is_semantic_duplicate,
    load_sent_store,
    record_from_alert,
    save_sent_store,
)
from finance_alert.env import ROOT
from finance_alert.macro import effective_min_setup_score, fetch_index_moves
from finance_alert.models import Alert
from finance_alert.performance_tracker import record_sent, update_forwards
from finance_alert.rvol_baseline import ensure_baseline
from finance_alert.rules import build_alerts
from finance_alert.sources import yahoo
from finance_alert.state_store import load_sent_raw, save_sent_raw

LAST = ROOT / "data" / "last_scan.json"


@dataclass
class ScanResult:
    now: datetime
    quotes: dict
    earnings: list
    news: list
    filings: list
    momentum: dict
    alerts: list[Alert]
    fresh: list[Alert]
    sources: dict[str, bool]
    macro_stress: bool = False
    min_setup_score: int = 6

    def summary(self) -> dict[str, Any]:
        return {
            "ts": self.now.isoformat(),
            "n_quotes": len(self.quotes),
            "n_earnings": len(self.earnings),
            "n_news": len(self.news),
            "n_filings": len(self.filings),
            "n_alerts": len(self.alerts),
            "n_new": len(self.fresh),
            "tipi": [a.tipo for a in self.fresh],
            "tickers": [a.ticker for a in self.fresh],
            "sources": self.sources,
            "macro_stress": self.macro_stress,
            "min_setup_score": self.min_setup_score,
        }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_sent() -> dict[str, str]:
    ids, _records = load_sent_store(load_sent_raw())
    return ids


def save_sent(ids: dict[str, str], records: list | None = None) -> None:
    cfg = load_config()
    keep = cfg.rules.dedupe.keep_days
    _, existing = load_sent_store(load_sent_raw(), keep_days=keep)
    merged = {r.key: r for r in existing}
    if records:
        for rec in records:
            merged[rec.key] = rec
    payload = save_sent_store(ids, list(merged.values()), keep_days=keep)
    save_sent_raw(payload)


def mark_sent(alerts: list[Alert], sent: dict[str, str] | None = None, quotes: dict | None = None) -> dict[str, str]:
    ids = sent if sent is not None else load_sent()
    now = _now_utc()
    records = [record_from_alert(a, now) for a in alerts]
    for alert in alerts:
        ids[alert.key] = now.isoformat()
    save_sent(ids, records)
    if quotes is not None:
        record_sent(alerts, quotes, sent_at=now)
    return ids


def filter_fresh(alerts: list[Alert], cfg: AppConfig | None = None) -> list[Alert]:
    cfg = cfg or load_config()
    dedupe = cfg.rules.dedupe
    ids, records = load_sent_store(load_sent_raw(), keep_days=dedupe.keep_days)
    fresh: list[Alert] = []
    for alert in alerts:
        if alert.key in ids:
            continue
        if is_semantic_duplicate(
            alert,
            records,
            threshold=dedupe.similarity_threshold,
            window_hours=dedupe.time_window_hours,
            llm_equiv=dedupe.llm_equivalence,
        ):
            continue
        fresh.append(alert)
    return fresh


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def write_last_scan(result: ScanResult) -> None:
    LAST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": result.summary(),
        "quotes": _jsonable(result.quotes),
        "earnings": _jsonable(result.earnings),
        "news": _jsonable(result.news[:40]),
        "filings": _jsonable(result.filings),
        "alerts": [a.as_dict() for a in result.alerts],
        "fresh": [a.as_dict() for a in result.fresh],
    }
    LAST.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _macro_quotes(cfg: AppConfig, base: dict) -> dict:
    etfs = cfg.rules.macro.etfs or []
    missing = [s for s in etfs if s not in base]
    if not missing:
        return base
    extra = fetch_quotes(missing)
    ext = yahoo.fetch_session_quotes(missing)
    for sym, q in ext.items():
        if sym in extra:
            extra[sym].session = q.session
            if q.change_pct is not None:
                extra[sym].change_pct = q.change_pct
            if q.price is not None:
                extra[sym].price = q.price
        else:
            extra[sym] = q
    base.update(extra)
    return base


def run_scan(cfg: AppConfig | None = None) -> ScanResult:
    cfg = cfg or load_config()
    now = _now_utc()
    sources = source_status()

    ensure_baseline(cfg.symbols)
    update_forwards(now)

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_quotes = pool.submit(fetch_quotes, cfg.symbols)
        f_earn = pool.submit(fetch_earnings, cfg, now)
        f_news = pool.submit(fetch_news, cfg, now)
        f_filings = pool.submit(fetch_filings, cfg)
        quotes = f_quotes.result()
        earnings = f_earn.result()
        news = f_news.result()
        filings = f_filings.result()

    quotes = overlay_extended_hours(quotes, cfg.symbols)
    quotes = _macro_quotes(cfg, quotes)
    quotes = overlay_volume_stats(quotes)

    index_moves = fetch_index_moves(cfg.rules.macro.etfs, quotes)
    min_score = effective_min_setup_score(cfg.rules.macro, index_moves)
    macro_stress = min_score > cfg.rules.macro.normal_min_setup_score

    movers = []
    for ticker, quote in quotes.items():
        pct = quote.pct_from_close()
        if pct is not None and abs(pct) >= 1.5:
            movers.append(ticker)
    for ev in earnings:
        if ev.ticker not in movers:
            movers.append(ev.ticker)
    momentum: dict[str, float] = {}
    if movers:
        momentum = fetch_momentum(movers[:8], cfg.rules.momentum_minutes)

    alerts = build_alerts(
        cfg=cfg,
        now=now,
        quotes=quotes,
        earnings=earnings,
        news=news,
        filings=filings,
        momentum=momentum,
        min_setup_score=min_score,
    )
    fresh = filter_fresh(alerts, cfg)
    result = ScanResult(
        now=now,
        quotes=quotes,
        earnings=earnings,
        news=news,
        filings=filings,
        momentum=momentum,
        alerts=alerts,
        fresh=fresh,
        sources=sources,
        macro_stress=macro_stress,
        min_setup_score=min_score,
    )
    write_last_scan(result)
    return result
