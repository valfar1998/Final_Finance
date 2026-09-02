"""Parse analyst consensus / rating dates from API payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc


def yahoo_trend_period_to_date(period: str) -> str | None:
    """Yahoo recommendationTrend period e.g. '0m', '-1m' → first day of that month."""
    if not period or not period.endswith("m"):
        return None
    try:
        offset = int(period[:-1])
    except ValueError:
        return None
    today = datetime.now(UTC)
    month = today.month + offset
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return f"{year}-{month:02d}-01"


def dates_from_yahoo_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Latest rating and price-target dates from upgradeDowngradeHistory."""
    if not history:
        return {}

    sorted_hist = sorted(
        history,
        key=lambda h: int(h.get("epochGradeDate") or 0),
        reverse=True,
    )
    latest = sorted_hist[0]
    last_rating_date = _epoch_to_date(latest.get("epochGradeDate"))

    last_target_date = None
    last_target_firm = None
    last_target_value = None
    for item in sorted_hist:
        target = item.get("currentPriceTarget") or item.get("priceTarget")
        if target is not None and float(target) > 0:
            last_target_date = _epoch_to_date(item.get("epochGradeDate"))
            last_target_firm = item.get("firm")
            last_target_value = float(target)
            break

    return {
        "analyst_last_rating_date": last_rating_date,
        "analyst_last_target_date": last_target_date,
        "analyst_last_firm": last_target_firm,
        "analyst_last_target_value": last_target_value,
    }


def merge_analyst_dates(result: dict[str, Any]) -> dict[str, Any]:
    """Append human-readable date hints to recommendation_label."""
    parts: list[str] = []

    consensus = result.get("analyst_consensus_date")
    if consensus:
        parts.append(f"consenso {format_date_it(consensus)}")

    target_date = result.get("analyst_last_target_date")
    if target_date:
        firm = result.get("analyst_last_firm")
        chunk = f"ultimo target {format_date_it(target_date)}"
        if firm:
            chunk += f" ({firm})"
        parts.append(chunk)
    elif result.get("analyst_last_rating_date"):
        rating_date = result["analyst_last_rating_date"]
        firm = result.get("analyst_last_firm")
        chunk = f"ultimo rating {format_date_it(rating_date)}"
        if firm:
            chunk += f" ({firm})"
        parts.append(chunk)

    if parts:
        suffix = " · ".join(parts)
        label = result.get("recommendation_label") or ""
        if suffix not in label:
            result["recommendation_label"] = f"{label} · {suffix}" if label else suffix

    return result


def format_date_it(iso_date: str | None) -> str:
    """YYYY-MM-DD → DD/MM/YYYY for display."""
    if not iso_date:
        return "—"
    try:
        d = datetime.strptime(iso_date[:10], "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso_date[:10]


def days_since(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        d = datetime.strptime(iso_date[:10], "%Y-%m-%d").replace(tzinfo=UTC)
        return (datetime.now(UTC) - d).days
    except ValueError:
        return None


def freshness_label(iso_date: str | None) -> str | None:
    """Short Italian freshness hint."""
    days = days_since(iso_date)
    if days is None:
        return None
    if days <= 30:
        return "recente"
    if days <= 90:
        return f"{days} gg fa"
    if days <= 365:
        months = days // 30
        return f"~{months} mesi fa"
    return f">{days // 365} anni fa"


def _epoch_to_date(epoch: Any) -> str | None:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None
