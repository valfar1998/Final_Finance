from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from finance_alert.env import env_key
from finance_alert.http import HttpError, get_json, map_parallel
from finance_alert.models import NewsItem, Quote, parse_num

BASE = "https://api.polygon.io"

# Snapshot live (full market / per-ticker) richiede piano a pagamento su Polygon/Massive.
# Sul free tier usiamo solo dati storici/EOD compatibili (es. grouped daily).
_SNAPSHOT_FORBIDDEN = False


def available() -> bool:
    return bool(env_key("POLYGON_API_KEY"))


def _key() -> str:
    return env_key("POLYGON_API_KEY")


def snapshot_available() -> bool:
    """True solo se lo snapshot live non ha già restituito 403 in questa run."""
    return available() and not _SNAPSHOT_FORBIDDEN


def _mark_snapshot_forbidden() -> None:
    global _SNAPSHOT_FORBIDDEN
    _SNAPSHOT_FORBIDDEN = True


def _fetch_one_quote(ticker: str) -> Quote | None:
    if not snapshot_available():
        return None
    us = ticker.split(".")[0].upper()
    try:
        data = get_json(
            f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers/{us}",
            params={"apiKey": _key()},
        )
    except HttpError as exc:
        if exc.status in {401, 403}:
            _mark_snapshot_forbidden()
        return None
    except (OSError, TimeoutError, ValueError):
        return None
    ticker_block = (data or {}).get("ticker") if isinstance(data, dict) else None
    if not isinstance(ticker_block, dict):
        return None
    day = ticker_block.get("day") or {}
    prev = ticker_block.get("prevDay") or {}
    last = ticker_block.get("lastTrade") or ticker_block.get("min") or {}
    price = parse_num(last.get("p") or day.get("c"))
    previous = parse_num(prev.get("c"))
    pct = parse_num(ticker_block.get("todaysChangePerc"))
    if price is None:
        return None
    return Quote(
        ticker=ticker,
        price=price,
        previous_close=previous,
        change_pct=pct,
        source="polygon",
    )


def fetch_quotes(tickers: list[str]) -> dict[str, Quote]:
    if not available() or not tickers:
        return {}
    results = map_parallel(_fetch_one_quote, tickers, max_workers=min(6, len(tickers)))
    return {q.ticker: q for q in results if q is not None}


def _prev_weekday(from_day: date | None = None) -> date:
    day = from_day or date.today()
    for i in range(1, 10):
        cand = day - timedelta(days=i)
        if cand.weekday() < 5:
            return cand
    return day - timedelta(days=1)


def _is_plain_us_symbol(sym: str) -> bool:
    s = sym.strip().upper()
    if not s or not s.isascii():
        return False
    if any(ch in s for ch in (".", "-", "^", "/", "=")):
        return False
    if len(s) > 5:
        return False
    if not s.isalnum() or not any(c.isalpha() for c in s):
        return False
    # Warrant / unit / right spesso finiscono con W/U/R su ticker corti — filtro soft
    if len(s) >= 5 and s[-1] in {"W", "U", "R"} and s[:-1].isalpha():
        return False
    # Simboli di test NASDAQ
    if s.endswith("ZZZT") or s in {"ZVZZT", "ZWZZT", "ZXZZT"}:
        return False
    return True


def fetch_prev_day_movers(
    *,
    min_abs_pct: float = 5.0,
    min_volume: float = 1_000_000.0,
    min_price: float = 2.0,
    limit: int = 40,
    upside_only: bool = True,
) -> list[str]:
    """
    Top mover del giorno di borsa precedente via grouped daily (1 HTTP, free tier OK).

    Utile in premarket: titoli che hanno già corso / gap overnight entrano nello scan
    Yahoo extended-hours. NON è uno snapshot live (quello è a pagamento).
    """
    if not available() or limit <= 0:
        return []
    day = _prev_weekday()
    try:
        data = get_json(
            f"{BASE}/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}",
            params={"adjusted": "true", "apiKey": _key()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = (data or {}).get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []

    scored: list[tuple[float, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        sym = str(row.get("T") or "").strip().upper()
        if not _is_plain_us_symbol(sym):
            continue
        open_px = parse_num(row.get("o"))
        close_px = parse_num(row.get("c"))
        vol = parse_num(row.get("v"))
        if open_px is None or close_px is None or vol is None:
            continue
        if open_px < min_price or close_px < min_price or vol < min_volume:
            continue
        pct = (close_px - open_px) / open_px * 100.0
        if upside_only and pct < min_abs_pct:
            continue
        if not upside_only and abs(pct) < min_abs_pct:
            continue
        scored.append((pct if upside_only else abs(pct), sym))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[str] = []
    seen: set[str] = set()
    for _, sym in scored:
        if sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
        if len(out) >= limit:
            break
    return out


def fetch_news(ticker: str, limit: int = 15) -> list[NewsItem]:
    if not available():
        return []
    us = ticker.split(".")[0].upper()
    try:
        data = get_json(
            f"{BASE}/v2/reference/news",
            params={"ticker": us, "limit": limit, "apiKey": _key()},
        )
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    rows = (data or {}).get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    items: list[NewsItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        headline = str(row.get("title") or "").strip()
        if not headline:
            continue
        published = None
        raw = str(row.get("published_utc") or "")
        if raw:
            try:
                published = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                published = None
        items.append(
            NewsItem(
                ticker=ticker,
                headline=headline,
                url=str(row.get("article_url") or ""),
                published=published,
                source="polygon",
                publisher=str(row.get("publisher", {}).get("name") if isinstance(row.get("publisher"), dict) else row.get("author") or ""),
            )
        )
    return items
