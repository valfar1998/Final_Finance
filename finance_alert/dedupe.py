"""Dedupe ibrido: stesso ticker + finestra temporale + Jaccard o equivalenza LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from finance_alert.models import Alert

_STOP = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at", "is", "are",
    "was", "were", "with", "after", "before", "from", "its", "it", "as", "by", "be",
    "il", "la", "di", "da", "per", "con", "su", "che", "non", "un", "una",
}


def _normalize(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOP}


def headline_similarity(a: str, b: str) -> float:
    sa, sb = _normalize(a), _normalize(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


@dataclass
class SentRecord:
    key: str
    ts: datetime
    ticker: str
    headline: str
    tipo: str


def _parse_ts(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


def load_sent_store(raw: dict | list | None, *, keep_days: int = 21) -> tuple[dict[str, str], list[SentRecord]]:
    """Legge telegram_alerts_sent.json (flat o con _meta)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    ids: dict[str, str] = {}
    records: list[SentRecord] = []

    if isinstance(raw, list):
        now = datetime.now(timezone.utc).isoformat()
        return {str(k): now for k in raw}, records

    if not isinstance(raw, dict):
        return ids, records

    meta = raw.get("_meta") if isinstance(raw.get("_meta"), dict) else {}
    for key, value in raw.items():
        if str(key).startswith("_"):
            continue
        ts = _parse_ts(value)
        if ts is None or ts < cutoff:
            continue
        ids[str(key)] = ts.isoformat()
        block = meta.get(str(key)) if isinstance(meta.get(str(key)), dict) else {}
        records.append(
            SentRecord(
                key=str(key),
                ts=ts,
                ticker=str(block.get("ticker") or "").upper(),
                headline=str(block.get("headline") or ""),
                tipo=str(block.get("tipo") or ""),
            )
        )
    return ids, records


def save_sent_store(ids: dict[str, str], records: list[SentRecord], *, keep_days: int = 21) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    kept_ids: dict[str, str] = {}
    kept_meta: dict[str, dict[str, str]] = {}
    rec_by_key = {r.key: r for r in records}

    for key, ts in ids.items():
        when = _parse_ts(ts)
        if when is None or when < cutoff:
            continue
        kept_ids[key] = when.isoformat()
        rec = rec_by_key.get(key)
        if rec:
            kept_meta[key] = {
                "ticker": rec.ticker,
                "headline": rec.headline,
                "tipo": rec.tipo,
            }

    payload: dict = dict(kept_ids)
    if kept_meta:
        payload["_meta"] = kept_meta
    return payload


def alert_headline(alert: Alert) -> str:
    if alert.tipo == "news":
        first = alert.body.split("\n", 1)[0].strip()
        return first or alert.titolo
    return alert.titolo


def is_semantic_duplicate(
    alert: Alert,
    records: list[SentRecord],
    *,
    threshold: float = 0.65,
    same_tipo: bool = True,
    window_hours: float = 2.0,
    llm_equiv: bool = True,
    now: datetime | None = None,
) -> bool:
    headline = alert_headline(alert)
    ticker = alert.ticker.upper()
    ref = now or datetime.now(timezone.utc)
    cutoff = ref - timedelta(hours=window_hours)

    for rec in records:
        if rec.ticker and rec.ticker != ticker:
            continue
        if rec.ts < cutoff:
            continue
        if same_tipo and rec.tipo and rec.tipo != alert.tipo:
            continue
        sim = headline_similarity(headline, rec.headline)
        if sim >= threshold:
            return True
        if llm_equiv and sim >= 0.25 and rec.headline:
            from finance_alert.news_llm import headlines_equivalent

            if headlines_equivalent(headline, rec.headline, ticker=ticker):
                return True
    return False


def record_from_alert(alert: Alert, ts: datetime | None = None) -> SentRecord:
    when = ts or datetime.now(timezone.utc)
    return SentRecord(
        key=alert.key,
        ts=when,
        ticker=alert.ticker.upper(),
        headline=alert_headline(alert),
        tipo=alert.tipo,
    )


def dumps_store(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)
