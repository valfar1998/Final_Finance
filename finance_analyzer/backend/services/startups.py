"""Startup / cheap stock picks with positive analyst outlook."""

from __future__ import annotations

import json
from typing import Any

from assets import DEFAULT_ASSETS, STARTUP_MAX_PRICE_USD, STARTUP_MIN_BUYABILITY, STARTUP_MIN_UPSIDE_PCT
from services.analyst_consensus import target_range_spread_pct
from services.cache_db import get_conn


def row_target_spread(row: dict[str, Any]) -> float | None:
    spread = row.get("analyst_target_spread_pct")
    if spread is not None:
        return float(spread)
    return target_range_spread_pct(
        row.get("analyst_target_low"),
        row.get("analyst_target_high"),
        row.get("analyst_target_mean"),
    )


def passes_startup_filters(
    row: dict[str, Any],
    min_analysts: int = 0,
    max_target_spread_pct: float = 0,
) -> bool:
    count = int(row.get("analyst_count") or 0)
    if min_analysts > 0 and count < min_analysts:
        return False
    if max_target_spread_pct > 0:
        spread = row_target_spread(row)
        if spread is None or spread > max_target_spread_pct:
            return False
    return True


def is_startup_pick(row: dict[str, Any]) -> bool:
    if row.get("type") != "azione":
        return False
    price = row.get("current_price")
    buy = row.get("buyability_pct")
    upside = row.get("analyst_upside_pct")
    mcap = row.get("market_cap")

    cheap = bool(
        (price is not None and price <= STARTUP_MAX_PRICE_USD)
        or (mcap is not None and mcap <= 20_000_000_000)
        or row.get("is_startup_candidate")
    )
    recommended = bool(
        (buy is not None and buy >= STARTUP_MIN_BUYABILITY)
        or (upside is not None and upside >= STARTUP_MIN_UPSIDE_PCT)
    )
    return cheap and recommended


def is_featured_startup(row: dict[str, Any]) -> bool:
    """Featured tickers: show if cheap + any positive analyst signal."""
    if not row.get("is_startup_candidate") or row.get("type") != "azione":
        return False
    price = row.get("current_price")
    if price is not None and price > STARTUP_MAX_PRICE_USD:
        return False
    buy = row.get("buyability_pct")
    upside = row.get("analyst_upside_pct")
    return bool(
        (buy is not None and buy >= 40)
        or (upside is not None and upside >= 5)
        or row.get("analyst_count", 0) > 0
    )


def search_startups_from_cache(
    region: str = "all",
    limit: int = 500,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT data_json FROM analysis_cache ORDER BY updated_at DESC LIMIT 8000"
        ).fetchall()

    picks: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = json.loads(row["data_json"])
        if region != "all" and data.get("region") != region:
            continue
        if is_startup_pick(data) or is_featured_startup(data):
            picks[data["id"]] = data

    return sorted(
        picks.values(),
        key=lambda r: (-(r.get("buyability_pct") or 0), -(r.get("analyst_upside_pct") or 0)),
    )[:limit]


def featured_startup_assets(region: str = "all") -> list[dict[str, Any]]:
    assets = []
    for feat in DEFAULT_ASSETS:
        if not feat.get("startup") or feat["type"] != "azione":
            continue
        if region != "all" and feat.get("region") != region:
            continue
        assets.append(feat)
    return assets
