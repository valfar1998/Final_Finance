"""Financial Modeling Prep API (free tier: 250 req/day, mainly US)."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd

from services.analyst_consensus import build_consensus

FMP_BASE = "https://financialmodelingprep.com"


def _key() -> str | None:
    return os.environ.get("FMP_API_KEY")


def fetch_fmp_history(ticker: str) -> pd.Series | None:
    """Daily close prices (up to ~5y on free tier for US symbols)."""
    api_key = _key()
    if not api_key:
        return None

    sym = ticker.split(".")[0].upper()
    url = f"{FMP_BASE}/api/v3/historical-price-full/{sym}"
    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(url, params={"apikey": api_key})
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, list) or not data:
            return None
        rows = []
        for row in data:
            d = row.get("date")
            c = row.get("close") or row.get("adjClose")
            if d and c is not None:
                rows.append((pd.Timestamp(d), float(c)))
        if not rows:
            return None
        series = pd.Series({d: v for d, v in rows}).sort_index()
        series.index = pd.to_datetime(series.index).tz_localize(None)
        return series.astype(float)
    except Exception:
        return None


def fetch_fmp_analysts(ticker: str, current_price: float | None = None) -> dict[str, Any] | None:
    """Buy/Hold/Sell consensus + target price from FMP."""
    api_key = _key()
    if not api_key:
        return None

    sym = ticker.split(".")[0].upper()
    target_mean = target_low = target_high = None

    try:
        with httpx.Client(timeout=20.0) as client:
            target_resp = client.get(
                f"{FMP_BASE}/api/v4/price-target-consensus",
                params={"symbol": sym, "apikey": api_key},
            )
            if target_resp.status_code == 200:
                tdata = target_resp.json()
                if tdata:
                    row = tdata[0] if isinstance(tdata, list) else tdata
                    target_mean = row.get("targetConsensus") or row.get("targetMedian")
                    target_low = row.get("targetLow")
                    target_high = row.get("targetHigh")
                    if target_mean is not None:
                        target_mean = float(target_mean)

            rec_resp = client.get(
                f"{FMP_BASE}/api/v4/upgrades-downgrades-consensus",
                params={"symbol": sym, "apikey": api_key},
            )
            if rec_resp.status_code == 200:
                rdata = rec_resp.json()
                if rdata:
                    row = rdata[0] if isinstance(rdata, list) else rdata
                    result = build_consensus(
                        strong_buy=int(row.get("strongBuy") or 0),
                        buy=int(row.get("buy") or 0),
                        hold=int(row.get("hold") or 0),
                        sell=int(row.get("sell") or 0),
                        strong_sell=int(row.get("strongSell") or 0),
                        source="fmp",
                        target_mean=target_mean,
                        target_low=float(target_low) if target_low is not None else None,
                        target_high=float(target_high) if target_high is not None else None,
                        current_price=current_price,
                    )
                    if result.get("buyability_pct") is not None:
                        return result

            # Fallback: solo target (senza % buy)
            if target_mean is not None:
                return build_consensus(
                    source="fmp",
                    target_mean=target_mean,
                    target_low=float(target_low) if target_low is not None else None,
                    target_high=float(target_high) if target_high is not None else None,
                    current_price=current_price,
                )
    except Exception:
        pass
    return None


def fetch_fmp_profile_name(ticker: str) -> str | None:
    api_key = _key()
    if not api_key:
        return None
    sym = ticker.split(".")[0].upper()
    url = f"{FMP_BASE}/api/v3/profile/{sym}"
    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, params={"apikey": api_key})
            resp.raise_for_status()
            data = resp.json()
        if data and isinstance(data, list):
            return data[0].get("companyName") or data[0].get("symbol")
    except Exception:
        pass
    return None
