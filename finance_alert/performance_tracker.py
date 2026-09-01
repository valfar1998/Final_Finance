"""Audit trail e forward-testing degli alert inviati (+1/+3/+7 giorni)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from finance_alert.aggregator import fetch_quotes
from finance_alert.env import ROOT
from finance_alert.models import Alert

TRACKER_PATH = ROOT / "data" / "performance_tracker.json"
_HORIZONS = (1, 3, 7)


def _load() -> dict[str, Any]:
    if not TRACKER_PATH.is_file():
        return {"records": [], "summary": {}}
    try:
        raw = json.loads(TRACKER_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"records": [], "summary": {}}
    if not isinstance(raw, dict):
        return {"records": [], "summary": {}}
    raw.setdefault("records", [])
    raw.setdefault("summary", {})
    return raw


def _save(payload: dict[str, Any]) -> None:
    TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACKER_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def _entry_from_alert(alert: Alert, quotes: dict) -> float | None:
    if alert.entry_price is not None:
        return float(alert.entry_price)
    quote = quotes.get(alert.ticker.upper())
    if quote and quote.price is not None:
        return float(quote.price)
    return None


def _classify(entry: float, target: float | None, stop: float | None, price: float) -> str:
    if target is not None and price >= target:
        return "win"
    if stop is not None and price <= stop:
        return "loss"
    if price > entry:
        return "partial_win"
    if price < entry:
        return "partial_loss"
    return "flat"


def _compute_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [r for r in records if r.get("outcome_7d") in {"win", "loss"}]
    if not closed:
        return {"n_closed": 0, "win_rate_pct": None, "avg_rr": None, "expectancy": None}
    wins = [r for r in closed if r.get("outcome_7d") == "win"]
    losses = [r for r in closed if r.get("outcome_7d") == "loss"]
    p_win = len(wins) / len(closed)
    p_loss = len(losses) / len(closed)
    target_hits = [r.get("target_pct") for r in wins if r.get("target_pct") is not None]
    stop_hits = [abs(r.get("stop_pct") or 0) for r in losses if r.get("stop_pct") is not None]
    avg_target = sum(target_hits) / len(target_hits) if target_hits else 0.0
    avg_stop = sum(stop_hits) / len(stop_hits) if stop_hits else 0.0
    expectancy = (p_win * avg_target) - (p_loss * avg_stop)
    rr = (avg_target / avg_stop) if avg_stop > 0 else None
    return {
        "n_closed": len(closed),
        "win_rate_pct": round(p_win * 100.0, 1),
        "avg_rr": round(rr, 2) if rr is not None else None,
        "expectancy": round(expectancy, 3),
    }


def record_sent(alerts: list[Alert], quotes: dict, *, sent_at: datetime | None = None) -> None:
    if not alerts:
        return
    when = sent_at or datetime.now(timezone.utc)
    payload = _load()
    known = {str(r.get("key")) for r in payload["records"]}
    for alert in alerts:
        if alert.key in known or alert.ticker == "*":
            continue
        entry = _entry_from_alert(alert, quotes)
        if entry is None:
            continue
        target = alert.target_price
        stop = alert.stop_price
        target_pct = ((target - entry) / entry * 100.0) if target else None
        stop_pct = ((entry - stop) / entry * 100.0) if stop else None
        payload["records"].append(
            {
                "key": alert.key,
                "ticker": alert.ticker,
                "tipo": alert.tipo,
                "sent_at": when.isoformat(),
                "entry_price": entry,
                "target_price": target,
                "stop_price": stop,
                "target_pct": target_pct,
                "stop_pct": stop_pct,
                "setup_score": alert.setup_score,
                "fwd": {f"{h}d": None for h in _HORIZONS},
                "outcome_7d": None,
            }
        )
    payload["summary"] = _compute_summary(payload["records"])
    _save(payload)


def update_forwards(now: datetime | None = None) -> dict[str, Any]:
    """Aggiorna prezzi forward per record maturi (+1/+3/+7g)."""
    when = now or datetime.now(timezone.utc)
    payload = _load()
    records: list[dict[str, Any]] = payload.get("records") or []
    if not records:
        return payload.get("summary") or {}

    pending_tickers: set[str] = set()
    for rec in records:
        sent = _parse_ts(rec.get("sent_at"))
        if sent is None:
            continue
        for days in _HORIZONS:
            key = f"{days}d"
            if rec.get("fwd", {}).get(key) is not None:
                continue
            if when - sent >= timedelta(days=days):
                pending_tickers.add(str(rec.get("ticker") or "").upper())

    quotes = fetch_quotes(sorted(pending_tickers)) if pending_tickers else {}

    for rec in records:
        sent = _parse_ts(rec.get("sent_at"))
        if sent is None:
            continue
        entry = rec.get("entry_price")
        target = rec.get("target_price")
        stop = rec.get("stop_price")
        ticker = str(rec.get("ticker") or "").upper()
        quote = quotes.get(ticker)
        price = float(quote.price) if quote and quote.price is not None else None
        fwd = rec.setdefault("fwd", {f"{h}d": None for h in _HORIZONS})
        for days in _HORIZONS:
            key = f"{days}d"
            if fwd.get(key) is not None:
                continue
            if when - sent < timedelta(days=days):
                continue
            if price is None or entry is None:
                continue
            outcome = _classify(float(entry), target, stop, price)
            fwd[key] = {"price": price, "outcome": outcome}
            if days == 7:
                rec["outcome_7d"] = outcome

    payload["summary"] = _compute_summary(records)
    _save(payload)
    return payload["summary"]


def summary() -> dict[str, Any]:
    return _load().get("summary") or {}
