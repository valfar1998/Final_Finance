"""Download and sync global stock universe into SQLite."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from services.cache_db import (
    count_by_region,
    count_by_type,
    count_symbols,
    get_meta,
    migrate_obbligazione_to_etf,
    set_meta,
    upsert_symbols,
)

NASDAQ_URLS = [
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
]

ETF_UNIVERSE_MAX_AGE_HOURS = int(os.environ.get("ETF_SYNC_MAX_AGE_HOURS", "24"))

# Finnhub exchange codes -> metadata
FINNHUB_EXCHANGES: list[dict[str, str]] = [
    {"exchange": "US", "region": "usa", "country": "USA", "stooq": "us", "yf": ""},
    {"exchange": "TO", "region": "canada", "country": "Canada", "stooq": "ca", "yf": ".TO"},
    {"exchange": "L", "region": "uk", "country": "Regno Unito", "stooq": "uk", "yf": ".L"},
    {"exchange": "MI", "region": "italia", "country": "Italia", "stooq": "it", "yf": ".MI"},
    {"exchange": "PA", "region": "europa", "country": "Francia", "stooq": "fr", "yf": ".PA"},
    {"exchange": "DE", "region": "europa", "country": "Germania (XETRA)", "stooq": "de", "yf": ".DE"},
    {"exchange": "AS", "region": "europa", "country": "Paesi Bassi", "stooq": "nl", "yf": ".AS"},
    {"exchange": "MC", "region": "europa", "country": "Spagna", "stooq": "es", "yf": ".MC"},
    {"exchange": "SW", "region": "europa", "country": "Svizzera", "stooq": "ch", "yf": ".SW"},
    {"exchange": "BE", "region": "europa", "country": "Belgio", "stooq": "be", "yf": ".BR"},
    {"exchange": "VI", "region": "europa", "country": "Austria", "stooq": "at", "yf": ".VI"},
    {"exchange": "HE", "region": "europa", "country": "Finlandia", "stooq": "fi", "yf": ".HE"},
    {"exchange": "ST", "region": "europa", "country": "Svezia", "stooq": "se", "yf": ".ST"},
    {"exchange": "OL", "region": "europa", "country": "Norvegia", "stooq": "no", "yf": ".OL"},
    {"exchange": "IR", "region": "europa", "country": "Irlanda", "stooq": "ie", "yf": ".IR"},
    {"exchange": "LS", "region": "europa", "country": "Portogallo", "stooq": "pt", "yf": ".LS"},
    {"exchange": "T", "region": "asia", "country": "Giappone (Tokyo)", "stooq": "jp", "yf": ".T"},
    {"exchange": "HK", "region": "asia", "country": "Hong Kong", "stooq": "hk", "yf": ".HK"},
    {"exchange": "SS", "region": "asia", "country": "Cina (Shanghai)", "stooq": "cn", "yf": ".SS"},
    {"exchange": "SZ", "region": "asia", "country": "Cina (Shenzhen)", "stooq": "cn", "yf": ".SZ"},
    {"exchange": "KS", "region": "asia", "country": "Corea del Sud", "stooq": "kr", "yf": ".KS"},
    {"exchange": "TW", "region": "asia", "country": "Taiwan", "stooq": "tw", "yf": ".TW"},
    {"exchange": "SI", "region": "asia", "country": "Singapore", "stooq": "sg", "yf": ".SI"},
]

SKIP_NAME_PATTERNS = re.compile(
    r"(ETF|ETN|FUND|TRUST|PREFERRED|WARRANT|UNIT|RIGHTS|NOTES|\^)",
    re.I,
)

ETF_NAME_HINT = re.compile(r"\b(ETF|ETN|ETP|UCITS|INDEX FUND)\b", re.I)
FINNHUB_ETF_TYPES = frozenset({"ETF", "ETP", "ETN", "EXCHANGE TRADED FUND"})


def _clean_id(*parts: str) -> str:
    return "_".join(p.lower().replace(".", "_").replace("/", "_") for p in parts if p)


def _is_common_stock(name: str, symbol: str) -> bool:
    if not symbol or len(symbol) > 15:
        return False
    if SKIP_NAME_PATTERNS.search(name or ""):
        return False
    if symbol.endswith(("W", "R", "U", "P")) and len(symbol) > 4:
        return False
    return True


def _is_etf_candidate(name: str, symbol: str) -> bool:
    if not symbol or len(symbol) > 15:
        return False
    if re.search(r"(WARRANT|UNIT|RIGHTS|\^)", name or "", re.I):
        return False
    if symbol.endswith(("W", "R", "U", "P")) and len(symbol) > 4:
        return False
    return True


def _parse_nasdaq_etf_row(url: str, parts: list[str]) -> tuple[str, str, str, str] | None:
    """Returns (symbol, name, etf_flag, test_issue) or None."""
    if "nasdaqlisted.txt" in url:
        if len(parts) < 7:
            return None
        return parts[0].strip().upper(), parts[1].strip(), parts[6].strip(), parts[3].strip()
    if len(parts) < 7:
        return None
    return parts[0].strip().upper(), parts[1].strip(), parts[4].strip(), parts[6].strip()


def sync_us_etfs() -> int:
    """ETF USA da NASDAQ Trader (colonna ETF=Y, ~3000+ titoli)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for url in NASDAQ_URLS:
            resp = client.get(url, headers={"User-Agent": "FinanceAnalyzer/1.0"})
            resp.raise_for_status()
            for line in resp.text.strip().splitlines()[1:]:
                if "|" not in line or line.startswith("File Creation"):
                    continue
                parts = line.split("|")
                parsed = _parse_nasdaq_etf_row(url, parts)
                if not parsed:
                    continue
                symbol, name, etf_flag, test_issue = parsed
                if test_issue == "Y" or etf_flag != "Y" or not symbol or symbol in seen:
                    continue
                if not _is_etf_candidate(name, symbol):
                    continue
                seen.add(symbol)
                sym_lower = symbol.lower()
                rows.append(
                    {
                        "id": _clean_id("etf", "us", symbol),
                        "symbol": symbol,
                        "name": name,
                        "yf_ticker": symbol,
                        "stooq_symbol": f"{sym_lower}.us",
                        "exchange": "NASDAQ/NYSE",
                        "region": "usa",
                        "country": "USA",
                        "type": "etf",
                        "currency": "USD",
                    }
                )

    return upsert_symbols(rows)


def _finnhub_is_etf(sym_type: str, name: str) -> bool:
    t = sym_type.upper().strip()
    if t in FINNHUB_ETF_TYPES:
        return True
    if t and t not in ("", "COMMON STOCK", "EQS", "STOCK"):
        return False
    return bool(ETF_NAME_HINT.search(name or ""))


def sync_finnhub_etfs(api_key: str) -> int:
    """ETF internazionali (e USA) via Finnhub."""
    total = 0
    with httpx.Client(timeout=90.0) as client:
        for ex in FINNHUB_EXCHANGES:
            url = (
                f"https://finnhub.io/api/v1/stock/symbol?"
                f"exchange={ex['exchange']}&token={api_key}"
            )
            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue

            rows: list[dict[str, Any]] = []
            for item in data:
                symbol = (item.get("symbol") or "").strip()
                name = (item.get("description") or symbol).strip()
                sym_type = (item.get("type") or "").strip()
                if not symbol or not _finnhub_is_etf(sym_type, name):
                    continue
                if not _is_etf_candidate(name, symbol):
                    continue

                if ex["exchange"] == "US":
                    base = symbol.upper()
                    yf_ticker = base
                    stooq_symbol = f"{base.lower()}.us"
                    region = "usa"
                    country = "USA"
                elif "." in symbol:
                    yf_ticker = symbol
                    base = symbol.split(".")[0]
                    stooq_symbol = f"{base.lower()}.{ex['stooq']}"
                    region = ex["region"]
                    country = ex["country"]
                else:
                    base = symbol
                    yf_ticker = f"{base}{ex['yf']}" if ex["yf"] else base
                    stooq_symbol = f"{base.lower()}.{ex['stooq']}"
                    region = ex["region"]
                    country = ex["country"]

                rows.append(
                    {
                        "id": _clean_id("etf", region, yf_ticker),
                        "symbol": base.upper(),
                        "name": name,
                        "yf_ticker": yf_ticker,
                        "stooq_symbol": stooq_symbol,
                        "exchange": ex["exchange"],
                        "region": region,
                        "country": country,
                        "type": "etf",
                        "currency": item.get("currency") or "",
                    }
                )

            total += upsert_symbols(rows)
    return total


def _etf_symbol_count() -> int:
    return count_symbols(asset_type="etf")


def _etf_universe_stale() -> bool:
    """True if ETF list was never synced or is older than ETF_UNIVERSE_MAX_AGE_HOURS."""
    last = get_meta("last_etf_sync")
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return age_h >= ETF_UNIVERSE_MAX_AGE_HOURS
    except (ValueError, TypeError):
        return True


def sync_etfs(force: bool = False) -> dict[str, Any]:
    """Sync ETF universe (USA NASDAQ + internazionale Finnhub)."""
    from assets import DEFAULT_ASSETS

    migrate_obbligazione_to_etf()

    etf_existing = _etf_symbol_count()
    finnhub_key = os.environ.get("FINNHUB_API_KEY")
    refresh = force or _etf_universe_stale()

    skip_us = etf_existing > 2500 and not refresh
    intl_etf = sum(
        count_symbols(region=r, asset_type="etf")
        for r in ("italia", "europa", "uk", "asia", "canada")
    )
    skip_intl = finnhub_key and intl_etf > 500 and not refresh

    if skip_us and (skip_intl or not finnhub_key) and not force:
        return {
            "status": "skipped",
            "message": (
                f"Universo ETF aggiornato di recente "
                f"(<{ETF_UNIVERSE_MAX_AGE_HOURS}h). Usa --force per risincronizzare."
            ),
            "total_etf": etf_existing,
            "by_type": count_by_type(),
            "by_region": count_by_region(),
            "last_etf_sync": get_meta("last_etf_sync"),
        }

    featured = [
        {
            "id": a["id"],
            "symbol": a.get("name", a["id"]).upper()[:12],
            "name": a["name"],
            "yf_ticker": a["yf"],
            "stooq_symbol": a["stooq"],
            "exchange": a.get("region", "featured"),
            "region": a.get("region", "usa"),
            "country": a.get("country", "—"),
            "type": "etf",
            "currency": "",
        }
        for a in DEFAULT_ASSETS
        if a.get("type") == "etf"
    ]
    upsert_symbols(featured)

    us_count = 0 if skip_us else sync_us_etfs()
    intl_count = 0
    if finnhub_key and not skip_intl:
        intl_count = sync_finnhub_etfs(finnhub_key)

    total_etf = _etf_symbol_count()
    set_meta("last_etf_sync", __import__("datetime").datetime.utcnow().isoformat())
    set_meta("etf_us_count", str(us_count))
    set_meta("etf_intl_count", str(intl_count))

    note_parts = []
    if not finnhub_key:
        note_parts.append(
            "Per ETF su Borsa Italiana, XETRA, Londra, ecc.: imposta FINNHUB_API_KEY e rilancia."
        )

    return {
        "status": "ok",
        "us_etf_added": us_count,
        "intl_etf_added": intl_count,
        "total_etf": total_etf,
        "by_type": count_by_type(),
        "by_region": count_by_region(),
        "finnhub_used": bool(finnhub_key),
        "last_etf_sync": get_meta("last_etf_sync"),
        "note": " ".join(note_parts) if note_parts else None,
    }


def sync_us_nasdaq() -> int:
    """Free US universe from NASDAQ Trader (~8000 symbols)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        for url in NASDAQ_URLS:
            resp = client.get(url, headers={"User-Agent": "FinanceAnalyzer/1.0"})
            resp.raise_for_status()
            lines = resp.text.strip().splitlines()
            for line in lines[1:]:
                if "|" not in line or line.startswith("File Creation"):
                    continue
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                symbol = parts[0].strip().upper()
                name = parts[1].strip()
                test_issue = parts[3].strip() if len(parts) > 3 else "N"
                if test_issue == "Y" or not symbol or symbol in seen:
                    continue
                if not _is_common_stock(name, symbol):
                    continue
                seen.add(symbol)
                sym_lower = symbol.lower()
                rows.append(
                    {
                        "id": _clean_id("us", symbol),
                        "symbol": symbol,
                        "name": name,
                        "yf_ticker": symbol,
                        "stooq_symbol": f"{sym_lower}.us",
                        "exchange": "NASDAQ/NYSE",
                        "region": "usa",
                        "country": "USA",
                        "type": "azione",
                        "currency": "USD",
                    }
                )

    return upsert_symbols(rows)


def sync_finnhub_exchanges(api_key: str) -> int:
    """International exchanges via Finnhub (free registration)."""
    total = 0
    with httpx.Client(timeout=90.0) as client:
        for ex in FINNHUB_EXCHANGES:
            if ex["exchange"] == "US":
                continue
            url = (
                f"https://finnhub.io/api/v1/stock/symbol?"
                f"exchange={ex['exchange']}&token={api_key}"
            )
            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue

            rows: list[dict[str, Any]] = []
            for item in data:
                symbol = (item.get("symbol") or "").strip()
                name = (item.get("description") or symbol).strip()
                sym_type = (item.get("type") or "").upper()
                if sym_type and sym_type not in ("COMMON STOCK", "EQS", "STOCK", ""):
                    continue
                if not symbol or not _is_common_stock(name, symbol):
                    continue

                if "." in symbol:
                    yf_ticker = symbol
                    base = symbol.split(".")[0]
                else:
                    base = symbol
                    yf_ticker = f"{base}{ex['yf']}" if ex["yf"] else base

                stooq_symbol = f"{base.lower()}.{ex['stooq']}"
                rows.append(
                    {
                        "id": _clean_id(ex["region"], yf_ticker),
                        "symbol": base.upper(),
                        "name": name,
                        "yf_ticker": yf_ticker,
                        "stooq_symbol": stooq_symbol,
                        "exchange": ex["exchange"],
                        "region": ex["region"],
                        "country": ex["country"],
                        "type": "azione",
                        "currency": item.get("currency") or "",
                    }
                )

            total += upsert_symbols(rows)
    return total


def _intl_symbol_count() -> int:
    by = count_by_region()
    return sum(v for k, v in by.items() if k != "usa")


def sync_universe(force: bool = False) -> dict[str, Any]:
    """Sync full universe. Returns stats."""
    from assets import DEFAULT_ASSETS

    existing = count_symbols()
    intl_existing = _intl_symbol_count()
    finnhub_key = os.environ.get("FINNHUB_API_KEY")

    # Salta solo se già completo (US + internazionale con Finnhub)
    skip_us = existing > 5000 and not force
    skip_intl = finnhub_key and intl_existing > 3000 and not force
    if skip_us and (skip_intl or not finnhub_key) and not force:
        return {
            "status": "skipped",
            "message": "Universo già popolato. Usa --force per risincronizzare.",
            "total": existing,
            "by_region": count_by_region(),
        }

    featured = [
        {
            "id": a["id"],
            "symbol": a.get("name", a["id"]).upper()[:12],
            "name": a["name"],
            "yf_ticker": a["yf"],
            "stooq_symbol": a["stooq"],
            "exchange": a.get("region", "featured"),
            "region": a.get("region", "usa"),
            "country": a.get("country", "—"),
            "type": a["type"],
            "currency": "",
        }
        for a in DEFAULT_ASSETS
    ]
    upsert_symbols(featured)

    us_count = 0 if skip_us else sync_us_nasdaq()
    intl_count = 0
    if finnhub_key and not skip_intl:
        intl_count = sync_finnhub_exchanges(finnhub_key)

    total = count_symbols()
    set_meta("last_sync", __import__("datetime").datetime.utcnow().isoformat())
    set_meta("us_count", str(us_count))
    set_meta("intl_count", str(intl_count))

    note_parts = []
    if not finnhub_key:
        note_parts.append(
            "Per Milano, Francoforte, Londra, Tokyo, Hong Kong, Canada e resto d'Europa/Asia: "
            "registrati gratis su finnhub.io e imposta FINNHUB_API_KEY, poi sync-universe.bat --force"
        )
    elif intl_count == 0:
        note_parts.append("Finnhub configurato ma nessun titolo internazionale scaricato. Riprova --force.")

    return {
        "status": "ok",
        "us_added": us_count,
        "intl_added": intl_count,
        "total": total,
        "by_region": count_by_region(),
        "finnhub_used": bool(finnhub_key),
        "note": " ".join(note_parts) if note_parts else None,
    }
