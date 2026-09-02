"""FastAPI backend for finance analyzer."""

from __future__ import annotations

from load_env import bootstrap_env

bootstrap_env()

import math
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from assets import (
    DEFAULT_ASSETS,
    REGIONS,
)
from services.analytics import (
    annual_return_cagr,
    chart_data,
    max_drawdown,
    volatility_annual,
    ytd_return,
)
from services.cache_db import (
    count_symbols,
    get_cached_analysis,
    get_meta,
    get_symbol_by_id,
    get_symbols_page,
    set_cached_analysis,
)
from services.forecast import monte_carlo_forecast
from services.startups import (
    featured_startup_assets,
    is_featured_startup,
    is_startup_pick,
    passes_startup_filters,
    row_target_spread,
    search_startups_from_cache,
)
from services.market_data import (
    get_analyst_buyability,
    get_close_prices,
    resolve_display_name,
)
from services.universe import sync_etfs, sync_universe

app = FastAPI(title="Finance Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY")
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50


def _symbol_to_asset(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row.get("name") or row["symbol"],
        "type": row.get("type") or "azione",
        "stooq": row["stooq_symbol"],
        "yf": row["yf_ticker"],
        "region": row.get("region", "usa"),
        "country": row.get("country", "—"),
        "startup": False,
    }


def analyze_asset(
    asset: dict[str, Any],
    *,
    include_chart: bool = True,
    use_cache: bool = True,
    skip_name_lookup: bool = False,
) -> dict[str, Any]:
    cache_key = asset["id"]
    if use_cache:
        cached = get_cached_analysis(cache_key)
        if cached:
            if not include_chart:
                cached = {**cached, "chart": []}
            return cached

    stooq = asset["stooq"]
    yf_ticker = asset.get("yf") or asset["stooq"].split(".")[0].upper()

    try:
        prices, price_source = get_close_prices(stooq, yf_ticker)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Dati non disponibili per {asset.get('name', yf_ticker)}: {exc}",
        ) from exc

    display_name = asset.get("name", yf_ticker)
    if not skip_name_lookup:
        display_name = resolve_display_name(display_name, yf_ticker)
    cagr = annual_return_cagr(prices)
    ytd = ytd_return(prices)
    vol = volatility_annual(prices)
    mdd = max_drawdown(prices)
    forecast = monte_carlo_forecast(prices, simulations=2000 if not include_chart else 5000)
    current_price = forecast.get("current_price")

    analyst = get_analyst_buyability(yf_ticker, asset["type"], current_price=current_price)

    result = {
        "id": asset["id"],
        "name": display_name,
        "symbol": asset.get("symbol") or asset.get("name"),
        "type": asset["type"],
        "region": asset.get("region", "usa"),
        "country": asset.get("country", "—"),
        "is_startup_candidate": asset.get("startup", False),
        "stooq_symbol": stooq,
        "yf_ticker": yf_ticker,
        "price_source": price_source,
        "rendimento_annuo_pct": cagr,
        "ytd_pct": ytd,
        "volatilita_annua_pct": vol,
        "max_drawdown_pct": mdd,
        "buyability_pct": analyst.get("buyability_pct"),
        "analyst_label": analyst.get("recommendation_label"),
        "analyst_count": analyst.get("analyst_count", 0),
        "analyst_source": analyst.get("source"),
        "analyst_buy_count": analyst.get("analyst_buy_count"),
        "analyst_hold_count": analyst.get("analyst_hold_count"),
        "analyst_sell_count": analyst.get("analyst_sell_count"),
        "analyst_consensus": analyst.get("analyst_consensus"),
        "analyst_target_mean": analyst.get("analyst_target_mean"),
        "analyst_target_low": analyst.get("analyst_target_low"),
        "analyst_target_high": analyst.get("analyst_target_high"),
        "analyst_upside_pct": analyst.get("analyst_upside_pct"),
        "analyst_target_spread_pct": analyst.get("analyst_target_spread_pct")
        or row_target_spread(analyst),
        "analyst_consensus_date": analyst.get("analyst_consensus_date"),
        "analyst_last_rating_date": analyst.get("analyst_last_rating_date"),
        "analyst_last_target_date": analyst.get("analyst_last_target_date"),
        "analyst_last_firm": analyst.get("analyst_last_firm"),
        "market_cap": analyst.get("market_cap"),
        "valore_atteso": analyst.get("analyst_target_mean") or forecast.get("forecast_price"),
        "current_price": current_price,
        "previsione_prezzo": forecast.get("forecast_price"),
        "previsione_range_basso": forecast.get("forecast_low"),
        "previsione_range_alto": forecast.get("forecast_high"),
        "previsione_rendimento_pct": forecast.get("forecast_return_pct"),
        "previsione_note": forecast.get("note"),
        "chart": chart_data(prices, max_points=120 if include_chart else 0) if include_chart else [],
        "data_points": len(prices),
        "last_date": prices.index[-1].strftime("%Y-%m-%d") if len(prices) else None,
    }

    if use_cache:
        set_cached_analysis(cache_key, result)

    if not include_chart:
        result["chart"] = []

    return result


def _collect_startups(
    region: str = "all",
    min_analysts: int = 0,
    max_target_spread_pct: float = 0,
    limit: int = 24,
) -> list[dict[str, Any]]:
    """Startup picks: featured tickers + cache, with optional quality filters."""
    picks: dict[str, dict[str, Any]] = {}

    for cached in search_startups_from_cache(region=region, limit=500):
        picks[cached["id"]] = cached

    for feat in featured_startup_assets(region):
        try:
            row = analyze_asset(feat, include_chart=False, use_cache=True)
            if is_startup_pick(row) or is_featured_startup(row):
                picks[row["id"]] = row
        except Exception:
            pass

    filtered = [
        r
        for r in picks.values()
        if passes_startup_filters(r, min_analysts, max_target_spread_pct)
    ]
    return sorted(
        filtered,
        key=lambda r: (
            -(r.get("buyability_pct") or 0),
            -(r.get("analyst_upside_pct") or 0),
            -(r.get("analyst_count") or 0),
        ),
    )[:limit]


def _sort_rows(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    def num(v: Any, default: float = float("-inf")) -> float:
        if v is None:
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    key_map = {
        "buyability_desc": lambda r: num(r.get("buyability_pct"), -1),
        "buyability_asc": lambda r: -num(r.get("buyability_pct"), 999),
        "previsione_desc": lambda r: num(r.get("previsione_rendimento_pct")),
        "previsione_asc": lambda r: -num(r.get("previsione_rendimento_pct"), float("inf")),
        "valore_atteso_desc": lambda r: num(r.get("valore_atteso")),
        "valore_atteso_asc": lambda r: -num(r.get("valore_atteso"), float("inf")),
        "prezzo_asc": lambda r: -num(r.get("current_price"), float("inf")),
        "prezzo_desc": lambda r: num(r.get("current_price")),
        "rendimento_desc": lambda r: num(r.get("rendimento_annuo_pct")),
        "ytd_desc": lambda r: num(r.get("ytd_pct")),
        "upside_desc": lambda r: num(r.get("analyst_upside_pct")),
    }
    fn = key_map.get(sort, key_map["buyability_desc"])
    return sorted(rows, key=fn, reverse=True)


def _placeholder_row(sym_row: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    """Riga tabella anche se l'analisi Yahoo fallisce (rate limit, ecc.)."""
    asset = _symbol_to_asset(sym_row)
    return {
        "id": asset["id"],
        "name": asset["name"],
        "symbol": sym_row.get("symbol") or asset["name"],
        "type": asset["type"],
        "region": asset.get("region", "usa"),
        "country": asset.get("country", "—"),
        "is_startup_candidate": False,
        "stooq_symbol": asset["stooq"],
        "yf_ticker": asset["yf"],
        "price_source": None,
        "rendimento_annuo_pct": None,
        "ytd_pct": None,
        "volatilita_annua_pct": None,
        "max_drawdown_pct": None,
        "buyability_pct": None,
        "analyst_label": error or "Dati non disponibili (riprova o clicca per dettaglio)",
        "analyst_count": 0,
        "analyst_source": None,
        "analyst_target_mean": None,
        "analyst_target_low": None,
        "analyst_target_high": None,
        "analyst_upside_pct": None,
        "market_cap": None,
        "valore_atteso": None,
        "current_price": None,
        "previsione_prezzo": None,
        "previsione_range_basso": None,
        "previsione_range_alto": None,
        "previsione_rendimento_pct": None,
        "previsione_note": error,
        "chart": [],
        "data_points": 0,
        "last_date": None,
        "analysis_error": error,
    }


def _analyze_page(symbols: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Analizza ogni simbolo in sequenza (evita rate limit Yahoo). Sempre N righe."""
    rows: list[dict] = []
    errors: list[dict] = []

    for sym_row in symbols:
        asset = _symbol_to_asset(sym_row)
        try:
            row = analyze_asset(
                asset,
                include_chart=False,
                use_cache=True,
                skip_name_lookup=True,
            )
            rows.append(row)
        except HTTPException as exc:
            msg = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            rows.append(_placeholder_row(sym_row, msg))
            errors.append({"id": asset["id"], "name": asset["name"], "error": msg})
        except Exception as exc:
            rows.append(_placeholder_row(sym_row, str(exc)))
            errors.append({"id": asset["id"], "name": asset["name"], "error": str(exc)})

    return rows, errors


@app.on_event("startup")
def startup_sync():
    """Auto-populate universe on first run."""
    if count_symbols() < 500:
        try:
            sync_universe(force=False)
        except Exception:
            pass
    if count_symbols(asset_type="etf") < 500:
        try:
            sync_etfs(force=False)
        except Exception:
            pass


@app.get("/api/health")
def health():
    from load_env import env_file_display
    from services.data_sources import primary_analyst_api_label, primary_price_api_label

    total = count_symbols()
    return {
        "status": "ok",
        "finnhub": bool(FINNHUB_KEY),
        "fmp": bool(os.environ.get("FMP_API_KEY")),
        "twelve_data": bool(os.environ.get("TWELVE_DATA_API_KEY")),
        "primary_price_api": primary_price_api_label(),
        "primary_analyst_api": primary_analyst_api_label(),
        "universe_size": total,
        "last_sync": get_meta("last_sync"),
        "env_file": env_file_display(),
    }


@app.get("/api/regions")
def list_regions():
    return REGIONS


@app.post("/api/universe/sync")
def universe_sync(force: bool = False):
    return sync_universe(force=force)


@app.post("/api/universe/sync-etf")
def universe_sync_etf(force: bool = False):
    return sync_etfs(force=force)


@app.get("/api/universe/stats")
def universe_stats():
    from services.cache_db import count_by_region, count_by_type

    total = count_symbols()
    from services.data_sources import primary_analyst_api_label, primary_price_api_label

    return {
        "total": total,
        "by_region": count_by_region(),
        "by_type": count_by_type(),
        "last_sync": get_meta("last_sync"),
        "last_etf_sync": get_meta("last_etf_sync"),
        "finnhub_configured": bool(FINNHUB_KEY),
        "fmp_configured": bool(os.environ.get("FMP_API_KEY")),
        "twelve_data_configured": bool(os.environ.get("TWELVE_DATA_API_KEY")),
        "primary_price_api": primary_price_api_label(),
        "primary_analyst_api": primary_analyst_api_label(),
    }


def _passes_filters(row: dict[str, Any], min_buyability: float, min_previsione_pct: float) -> bool:
    if min_buyability > 0:
        b = row.get("buyability_pct")
        if b is None or float(b) < min_buyability:
            return False
    if min_previsione_pct > 0:
        p = row.get("previsione_rendimento_pct")
        if p is None or float(p) < min_previsione_pct:
            return False
    return True


@app.get("/api/dashboard")
def dashboard(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    region: str = Query("all"),
    type: str = Query("all"),
    sort: str = Query("buyability_desc"),
    min_buyability: float = Query(0, ge=0, le=100),
    min_previsione_pct: float = Query(0, ge=-100, le=500),
    q: str = Query("", max_length=80),
):
    asset_type = type if type != "all" else None
    search = q.strip() or None
    region_filter = region if region != "all" else None
    total = count_symbols(region_filter, asset_type, search)
    if total == 0 and not search:
        sync_universe(force=False)
        total = count_symbols(region_filter, asset_type, search)

    total_pages = max(1, math.ceil(total / page_size))
    page = min(page, total_pages)

    symbols = get_symbols_page(
        page=page,
        page_size=page_size,
        region=region,
        asset_type=asset_type,
        sort=sort,
        search=search,
    )
    rows, errors = _analyze_page(symbols)
    rows = _sort_rows(rows, sort)
    rows = [r for r in rows if _passes_filters(r, min_buyability, min_previsione_pct)]

    return {
        "assets": rows,
        "errors": errors,
        "count": len(rows),
        "rows_requested": len(symbols),
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "regions": REGIONS,
        "filters_applied": {
            "min_buyability": min_buyability,
            "min_previsione_pct": min_previsione_pct,
            "q": search or "",
        },
    }


@app.get("/api/startups")
def list_startups(
    region: str = Query("all"),
    min_analysts: int = Query(0, ge=0, le=100),
    max_target_spread_pct: float = Query(0, ge=0, le=500),
):
    """Piccole azioni consigliate — filtri: min analisti, max spread range target %."""
    rows = _collect_startups(
        region=region,
        min_analysts=min_analysts,
        max_target_spread_pct=max_target_spread_pct,
    )
    return {
        "startups": rows,
        "count": len(rows),
        "filters_applied": {
            "min_analysts": min_analysts,
            "max_target_spread_pct": max_target_spread_pct,
        },
    }


@app.get("/api/asset/{asset_id}/recent")
def get_asset_recent(asset_id: str, days: int = Query(20, ge=5, le=60)):
    """Ultimi N giorni di prezzo (Stooq cache → Finnhub → Yahoo) per grafico dettaglio."""
    from services.recent_bars import get_recent_bars

    row = get_symbol_by_id(asset_id)
    if not row:
        asset = next((a for a in DEFAULT_ASSETS if a["id"] == asset_id), None)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset non trovato")
        stooq = asset["stooq"]
        yf = asset.get("yf") or asset["stooq"].split(".")[0].upper()
        name = asset.get("name", asset_id)
    else:
        stooq = row["stooq_symbol"]
        yf = row["yf_ticker"]
        name = row.get("name") or row["symbol"]

    try:
        data = get_recent_bars(stooq, yf, days=days)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "id": asset_id,
        "name": name,
        "stooq_symbol": stooq,
        "yf_ticker": yf,
        **data,
    }


@app.get("/api/asset/{asset_id}")
def get_asset(asset_id: str):
    row = get_symbol_by_id(asset_id)
    if row:
        return analyze_asset(_symbol_to_asset(row), include_chart=True, use_cache=True)

    asset = next((a for a in DEFAULT_ASSETS if a["id"] == asset_id), None)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset non trovato")
    return analyze_asset(asset, include_chart=True, use_cache=True)


@app.get("/api/chart/{asset_id}")
def get_chart(asset_id: str):
    data = get_asset(asset_id)
    return {"id": data["id"], "name": data["name"], "chart": data["chart"]}


@app.get("/api/custom")
def analyze_custom(
    stooq: str = Query(..., description="Simbolo Stooq es. aapl.us"),
    yf: str | None = Query(None, description="Ticker yfinance fallback"),
    name: str = Query("Custom", description="Nome visualizzato"),
    type: str = Query("azione", description="azione | etf"),
    region: str = Query("usa"),
    country: str = Query("—"),
):
    asset = {
        "id": stooq.replace(".", "_"),
        "name": name,
        "symbol": name,
        "type": type,
        "stooq": stooq.lower(),
        "yf": yf or stooq.split(".")[0].upper(),
        "region": region,
        "country": country,
    }
    return analyze_asset(asset, include_chart=True, use_cache=False)


@app.get("/api/portfolio")
def get_portfolio():
    from services.portfolio import list_portfolio

    return {"portfolio": list_portfolio(), "count": len(list_portfolio())}


@app.post("/api/portfolio")
def post_portfolio(
    ticker: str = Query(..., min_length=1, max_length=12),
    yf_ticker: str | None = Query(None),
    name: str = Query(""),
):
    from services.portfolio import add_to_portfolio

    add_to_portfolio(ticker, yf_ticker=yf_ticker, name=name)
    return {"ok": True, "ticker": ticker.upper()}


@app.delete("/api/portfolio/{ticker}")
def delete_portfolio(ticker: str):
    from services.portfolio import remove_from_portfolio

    ok = remove_from_portfolio(ticker)
    if not ok:
        raise HTTPException(status_code=404, detail="Ticker non in portafoglio")
    return {"ok": True, "removed": ticker.upper()}


@app.post("/api/portfolio/scan")
def scan_portfolio_endpoint(notify: bool = Query(True)):
    """Ricalcola analisi portafoglio + alert Telegram su variazioni buyability."""
    from services.portfolio import latest_snapshot, list_portfolio, record_score_snapshot
    from services.telegram_alerts import maybe_notify_buyability_change

    rows = list_portfolio()
    results: list[dict] = []
    for row in rows:
        ticker = row["ticker"]
        prev = latest_snapshot(ticker)
        old_buy = float(prev["buyability_pct"]) if prev and prev.get("buyability_pct") is not None else None
        asset = {
            "id": ticker.lower(),
            "name": row.get("name") or ticker,
            "type": "azione",
            "stooq": f"{(row.get('yf_ticker') or ticker).lower()}.us",
            "yf": row.get("yf_ticker") or ticker,
            "region": "usa",
            "country": "USA",
        }
        try:
            analysis = analyze_asset(asset, include_chart=False, use_cache=True)
        except HTTPException as exc:
            results.append({"ticker": ticker, "error": str(exc.detail)})
            continue
        record_score_snapshot(ticker, analysis)
        new_buy = analysis.get("buyability_pct")
        sent = False
        if notify:
            sent = maybe_notify_buyability_change(
                ticker,
                name=analysis.get("name") or ticker,
                old_buy=old_buy,
                new_buy=new_buy,
                price=analysis.get("current_price"),
                forecast_pct=analysis.get("previsione_rendimento_pct"),
            )
        results.append(
            {
                "ticker": ticker,
                "buyability_pct": new_buy,
                "previsione_rendimento_pct": analysis.get("previsione_rendimento_pct"),
                "notified": sent,
            }
        )
    return {"ok": True, "results": results, "count": len(results)}
