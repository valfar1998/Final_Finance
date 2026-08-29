from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from finance_alert.aggregator import (
    fetch_earnings,
    fetch_filings,
    fetch_momentum,
    fetch_news,
    fetch_quotes,
    overlay_extended_hours,
    source_status,
)
from finance_alert.config import AppConfig, load_config
from finance_alert.env import ROOT
from finance_alert.models import Alert
from finance_alert.rules import build_alerts

SENT = ROOT / "data" / "telegram_alerts_sent.json"
LAST = ROOT / "data" / "last_scan.json"
KEEP_DAYS = 21


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
        }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_sent() -> dict[str, str]:
    if not SENT.is_file():
        return {}
    try:
        raw = json.loads(SENT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(raw, list):
        return {str(k): _now_utc().isoformat() for k in raw}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    return {}


def save_sent(ids: dict[str, str]) -> None:
    cutoff = _now_utc() - timedelta(days=KEEP_DAYS)
    kept: dict[str, str] = {}
    for key, ts in ids.items():
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            when = _now_utc()
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            kept[key] = ts
    SENT.parent.mkdir(parents=True, exist_ok=True)
    SENT.write_text(json.dumps(kept, indent=2), encoding="utf-8")


def mark_sent(alerts: list[Alert], sent: dict[str, str] | None = None) -> dict[str, str]:
    ids = sent if sent is not None else load_sent()
    now = _now_utc().isoformat()
    for alert in alerts:
        ids[alert.key] = now
    save_sent(ids)
    return ids


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


def run_scan(cfg: AppConfig | None = None) -> ScanResult:
    cfg = cfg or load_config()
    now = _now_utc()
    sources = source_status()

    # Quote + earnings + news + filings sono indipendenti → in parallelo
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
    )
    sent = load_sent()
    fresh = [a for a in alerts if a.key not in sent]
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
    )
    write_last_scan(result)
    return result
