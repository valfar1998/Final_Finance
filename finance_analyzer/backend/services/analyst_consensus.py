"""Buy / Hold / Sell consensus from analyst counts (Trade Republic–style)."""

from __future__ import annotations

from typing import Any, Literal

ConsensusLabel = Literal["strong_buy", "buy", "hold", "sell", "strong_sell"]


def build_consensus(
    *,
    strong_buy: int = 0,
    buy: int = 0,
    hold: int = 0,
    sell: int = 0,
    strong_sell: int = 0,
    source: str,
    target_mean: float | None = None,
    target_low: float | None = None,
    target_high: float | None = None,
    current_price: float | None = None,
) -> dict[str, Any]:
    """
    buyability_pct = % analisti con rating Buy (Strong Buy + Buy).
    Allineato al modello usato da molte app (incluso Trade Republic).
    """
    sb = max(0, int(strong_buy))
    b = max(0, int(buy))
    h = max(0, int(hold))
    s = max(0, int(sell))
    ss = max(0, int(strong_sell))
    total = sb + b + h + s + ss

    result: dict[str, Any] = {
        "buyability_pct": None,
        "recommendation_label": "Nessun dato analisti",
        "analyst_count": total,
        "analyst_buy_count": sb + b,
        "analyst_hold_count": h,
        "analyst_sell_count": s + ss,
        "analyst_strong_buy_count": sb,
        "analyst_consensus": None,
        "analyst_target_mean": target_mean,
        "analyst_target_low": target_low,
        "analyst_target_high": target_high,
        "analyst_upside_pct": None,
        "market_cap": None,
        "source": source,
    }

    if target_mean is not None and current_price is not None and current_price > 0:
        result["analyst_upside_pct"] = round(
            ((target_mean - current_price) / current_price) * 100, 2
        )

    spread = target_range_spread_pct(target_low, target_high, target_mean)
    if spread is not None:
        result["analyst_target_spread_pct"] = spread

    if total <= 0:
        if target_mean is not None:
            label = f"Target medio {target_mean:.2f} (senza rating buy/hold/sell)"
            if target_low is not None and target_high is not None:
                label += f" · range {target_low:.0f}–{target_high:.0f}"
            result["recommendation_label"] = label
        return result

    buy_pct = round(((sb + b) / total) * 100, 1)
    result["buyability_pct"] = buy_pct
    result["analyst_consensus"] = _dominant_rating(sb, b, h, s, ss)
    result["recommendation_label"] = (
        f"{sb + b} Buy · {h} Hold · {s + ss} Sell su {total} analisti ({buy_pct}% Buy)"
    )
    if target_mean is not None:
        result["recommendation_label"] += f" · target {target_mean:.2f}"
        if result["analyst_upside_pct"] is not None:
            result["recommendation_label"] += f" ({result['analyst_upside_pct']:+.1f}% upside)"
        if target_low is not None and target_high is not None:
            result["recommendation_label"] += f" · range {target_low:.0f}–{target_high:.0f}"
            if spread is not None:
                result["recommendation_label"] += f" (spread {spread:.0f}%)"

    return result


def target_range_spread_pct(
    target_low: float | None,
    target_high: float | None,
    target_mean: float | None = None,
) -> float | None:
    """
    Ampiezza del range target analisti in % rispetto al target medio.
    Es. range 42–76 con media 59 → spread ~58%.
    Range 10–10 → spread 0%.
    """
    if target_low is None or target_high is None:
        return None
    low, high = float(target_low), float(target_high)
    if high < low:
        low, high = high, low
    mid = float(target_mean) if target_mean and target_mean > 0 else (low + high) / 2
    if mid <= 0:
        return None
    return round(((high - low) / mid) * 100, 1)


def _dominant_rating(sb: int, b: int, h: int, s: int, ss: int) -> str:
    counts = {
        "strong_buy": sb,
        "buy": b,
        "hold": h,
        "sell": s,
        "strong_sell": ss,
    }
    return max(counts, key=counts.get)  # type: ignore[arg-type]


def from_yfinance_mean(mean: float, count: int, source: str = "yfinance") -> dict[str, Any]:
    """Fallback: recommendationMean 1=Strong Buy … 5=Strong Sell."""
    # Approximate buy share from mean (1=all buy, 5=all sell)
    buy_pct = round(max(0.0, min(100.0, ((5.0 - float(mean)) / 4.0) * 100.0)), 1)
    label = "Buy" if buy_pct >= 60 else "Hold" if buy_pct >= 40 else "Sell"
    return {
        "buyability_pct": buy_pct,
        "recommendation_label": f"Consenso stimato {label} (media rating {mean:.2f}/5, {count} analisti)",
        "analyst_count": int(count),
        "analyst_buy_count": None,
        "analyst_hold_count": None,
        "analyst_sell_count": None,
        "analyst_strong_buy_count": None,
        "analyst_consensus": label.lower(),
        "analyst_target_mean": None,
        "analyst_target_low": None,
        "analyst_target_high": None,
        "analyst_upside_pct": None,
        "market_cap": None,
        "source": source,
    }
