"""Download and cache historical OHLCV data from Stooq CSV."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "stooq"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
STOOQ_URL_PL = "https://stooq.pl/q/d/l/?s={symbol}&i=d"


def _cache_path(symbol: str) -> Path:
    safe = symbol.lower().replace("/", "_")
    return CACHE_DIR / f"{safe}.csv"


def _is_valid_csv(text: str) -> bool:
    text = text.strip()
    return bool(text) and not text.startswith("<") and "Date,Open" in text[:80]


def fetch_stooq_history(symbol: str, max_age_hours: int = 12) -> pd.DataFrame:
    """
    Fetch daily history from Stooq. Symbol format: aapl.us, vwce.de, enel.it
    Returns DataFrame with columns: Date, Open, High, Low, Close, Volume
    """
    symbol = symbol.strip().lower()
    cache = _cache_path(symbol)

    if cache.exists():
        age = datetime.now() - datetime.fromtimestamp(cache.stat().st_mtime)
        if age < timedelta(hours=max_age_hours):
            df = pd.read_csv(cache, parse_dates=["Date"])
            if not df.empty:
                return df

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,*/*",
        "Referer": f"https://stooq.com/q/?s={symbol}",
    }

    last_error: Exception | None = None
    for base_url in (STOOQ_URL, STOOQ_URL_PL):
        url = base_url.format(symbol=symbol)
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                text = resp.text.strip()

            if not _is_valid_csv(text):
                raise ValueError(f"Risposta Stooq non valida (protezione anti-bot?)")

            df = pd.read_csv(io.StringIO(text), parse_dates=["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            df.to_csv(cache, index=False)
            return df
        except Exception as exc:
            last_error = exc

    raise ValueError(
        f"Nessun dato Stooq per '{symbol}'. "
        f"Esegui scripts/sync_stooq.py per scaricare i CSV. Dettaglio: {last_error}"
    )


def get_price_series(symbol: str) -> pd.Series:
    df = fetch_stooq_history(symbol)
    return df.set_index("Date")["Close"].astype(float)


def load_cached_only(symbol: str) -> pd.DataFrame | None:
    """Return cached Stooq CSV if present (any age)."""
    cache = _cache_path(symbol.strip().lower())
    if not cache.exists():
        return None
    df = pd.read_csv(cache, parse_dates=["Date"])
    return df if not df.empty else None
