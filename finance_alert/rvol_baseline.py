"""Profilo volume medio (20g, barre 5m) in cache — scan usa solo chart 1d."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from finance_alert.env import ROOT
from finance_alert.http import map_parallel
from finance_alert.sources import yahoo

BASELINE_PATH = ROOT / "data" / "rvol_baseline.json"
TZ_ROME = ZoneInfo("Europe/Rome")
BASELINE_RANGE = "1mo"
PROFILE_DAYS = 20


def _today_rome() -> str:
    return datetime.now(TZ_ROME).date().isoformat()


def load_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.is_file():
        return {}
    try:
        raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def needs_refresh(data: dict[str, Any] | None = None) -> bool:
    data = data if data is not None else load_baseline()
    return str(data.get("updated") or "") != _today_rome()


def _build_one(ticker: str) -> tuple[str, dict[str, Any] | None]:
    profile = yahoo.build_volume_profile(ticker, range_=BASELINE_RANGE, max_days=PROFILE_DAYS)
    if not profile:
        return ticker, None
    time.sleep(0.35)
    return ticker, profile


def build_baseline(tickers: list[str]) -> dict[str, Any]:
    tickers = [t.upper() for t in tickers if t]
    profiles: dict[str, Any] = {}
    if tickers:
        for ticker, prof in map_parallel(_build_one, tickers, max_workers=3):
            if prof:
                profiles[ticker] = prof
    payload = {
        "updated": _today_rome(),
        "range": BASELINE_RANGE,
        "days": PROFILE_DAYS,
        "tickers": profiles,
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"rvol baseline: {BASELINE_PATH} ({len(profiles)} ticker)")
    return payload


def ensure_baseline(tickers: list[str], *, force: bool = False) -> dict[str, Any]:
    data = load_baseline()
    if force or needs_refresh(data):
        return build_baseline(tickers)
    return data


def compute_live_rvol(
    ticker: str,
    session: str,
    baseline: dict[str, Any] | None = None,
) -> tuple[float | None, float | None, float | None]:
    """(volume_oggi, baseline_atteso, rvol) — una sola richiesta chart 1d."""
    data = baseline if baseline is not None else load_baseline()
    prof = (data.get("tickers") or {}).get(ticker.upper()) or {}
    sess = session if session in {"pre", "post", "regular"} else "regular"
    block = prof.get(sess) or {}
    session_avg = block.get("session_avg")
    slot_avgs: dict[str, float] = block.get("slots") or {}

    live = yahoo.fetch_today_session_stats(ticker, session=sess)
    if live is None:
        return None, None, None
    today_vol, slot_keys = live

    expected = 0.0
    if slot_keys and slot_avgs:
        for key in slot_keys:
            expected += float(slot_avgs.get(key) or 0.0)
    elif session_avg:
        expected = float(session_avg)

    if today_vol <= 0:
        return today_vol, expected or None, None
    if not expected or expected <= 0:
        return today_vol, session_avg, None
    return today_vol, expected, today_vol / expected
