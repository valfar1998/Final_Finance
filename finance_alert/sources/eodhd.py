"""EODHD REST — copertura multi-mercato (CN/HK/KR/US) per quote EOD/realtime.

Docs: https://eodhd.com/financial-apis/
Free/paid key: EODHD_API_TOKEN
"""

from __future__ import annotations

from datetime import datetime, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import Quote, parse_num

BASE = "https://eodhd.com/api"


def available() -> bool:
    return bool(env_key("EODHD_API_TOKEN"))


def _token() -> str:
    return env_key("EODHD_API_TOKEN")


def to_eodhd_symbol(ticker: str) -> str:
    """Yahoo-style → EODHD (Shanghai .SS → .SH)."""
    t = ticker.strip().upper()
    if not t:
        return t
    if t.endswith(".SS"):
        return t[:-3] + ".SH"
    if "." in t:
        return t
    # bare US ticker
    return f"{t}.US"


def from_eodhd_symbol(symbol: str, fallback: str) -> str:
    """EODHD symbol back toward Yahoo/watchlist form."""
    s = symbol.strip().upper()
    if s.endswith(".SH"):
        return s[:-3] + ".SS"
    if s.endswith(".US"):
        return s[:-3]
    return fallback.upper() if fallback else s


def fetch_quote(ticker: str) -> Quote | None:
    if not available():
        return None
    sym = to_eodhd_symbol(ticker)
    try:
        data = get_json(
            f"{BASE}/real-time/{sym}",
            params={"api_token": _token(), "fmt": "json"},
            timeout=15.0,
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        data = None
    q = _quote_from_realtime(ticker, data if isinstance(data, dict) else None)
    if q is not None:
        return q
    return _quote_from_eod(ticker, sym)


def _quote_from_realtime(ticker: str, data: dict | None) -> Quote | None:
    if not data:
        return None
    price = parse_num(data.get("close") if data.get("close") not in ("NA", None) else None)
    prev = parse_num(data.get("previousClose") if data.get("previousClose") not in ("NA", None) else None)
    pct = parse_num(data.get("change_p") if data.get("change_p") not in ("NA", None) else None)
    if price in (None, 0) and prev in (None, 0):
        return None
    ts = None
    raw_t = data.get("timestamp")
    if raw_t not in (None, "NA", ""):
        try:
            ts = datetime.fromtimestamp(int(raw_t), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            ts = None
    return Quote(
        ticker=ticker.upper(),
        price=price,
        previous_close=prev,
        change_pct=pct,
        source="eodhd",
        ts=ts,
    )


def _quote_from_eod(ticker: str, sym: str) -> Quote | None:
    """Ultima barra EOD se realtime non disponibile sul piano free."""
    try:
        data = get_json(
            f"{BASE}/eod/{sym}",
            params={"api_token": _token(), "fmt": "json", "order": "d", "from": "2025-01-01"},
            timeout=20.0,
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None
    last = data[-1] if isinstance(data[-1], dict) else None
    if not last:
        return None
    price = parse_num(last.get("close") or last.get("adjusted_close"))
    prev = None
    if len(data) >= 2 and isinstance(data[-2], dict):
        prev = parse_num(data[-2].get("close") or data[-2].get("adjusted_close"))
    pct = None
    if price is not None and prev not in (None, 0):
        pct = ((price - prev) / prev) * 100.0
    if price in (None, 0):
        return None
    return Quote(
        ticker=ticker.upper(),
        price=price,
        previous_close=prev,
        change_pct=pct,
        source="eodhd_eod",
        ts=None,
    )


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not available() or not tickers:
        return {}
    # Batch realtime (max ~15–20 per call); gaps → single + EOD fallback
    out: dict[str, Quote] = {}
    batch_size = 15
    for i in range(0, len(tickers), batch_size):
        chunk = tickers[i : i + batch_size]
        symbols = [to_eodhd_symbol(t) for t in chunk]
        joined = ",".join(symbols)
        try:
            data = get_json(
                f"{BASE}/real-time/{joined}",
                params={"api_token": _token(), "fmt": "json"},
                timeout=20.0,
            )
        except (HttpError, OSError, TimeoutError, ValueError):
            for t in chunk:
                q = fetch_quote(t)
                if q is not None:
                    out[q.ticker] = q
            continue
        rows: list[dict] = []
        if isinstance(data, list):
            rows = [r for r in data if isinstance(r, dict)]
        elif isinstance(data, dict):
            if "code" in data or "close" in data:
                rows = [data]
            else:
                rows = [v for v in data.values() if isinstance(v, dict)]
        by_code = {str(r.get("code") or "").upper(): r for r in rows}
        for orig, sym in zip(chunk, symbols):
            row = by_code.get(sym.upper())
            q = _quote_from_realtime(orig, row)
            if q is None:
                q = fetch_quote(orig)
            if q is not None:
                out[q.ticker] = q
    return out
