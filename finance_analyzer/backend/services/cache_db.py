"""SQLite storage for symbol universe and analysis cache."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "finance.db"


def _ensure_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS symbols (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT,
                yf_ticker TEXT NOT NULL,
                stooq_symbol TEXT NOT NULL,
                exchange TEXT,
                region TEXT NOT NULL,
                country TEXT,
                type TEXT DEFAULT 'azione',
                currency TEXT,
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_symbols_region ON symbols(region);
            CREATE INDEX IF NOT EXISTS idx_symbols_exchange ON symbols(exchange);
            CREATE INDEX IF NOT EXISTS idx_symbols_yf ON symbols(yf_ticker);

            CREATE TABLE IF NOT EXISTS analysis_cache (
                symbol_id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(symbol_id) REFERENCES symbols(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cache_updated ON analysis_cache(updated_at);

            CREATE TABLE IF NOT EXISTS universe_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_symbols(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.executemany(
            """
            INSERT INTO symbols (id, symbol, name, yf_ticker, stooq_symbol, exchange,
                                 region, country, type, currency, updated_at)
            VALUES (:id, :symbol, :name, :yf_ticker, :stooq_symbol, :exchange,
                    :region, :country, :type, :currency, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                symbol=excluded.symbol, name=excluded.name, yf_ticker=excluded.yf_ticker,
                stooq_symbol=excluded.stooq_symbol, exchange=excluded.exchange,
                region=excluded.region, country=excluded.country, type=excluded.type,
                currency=excluded.currency, updated_at=excluded.updated_at
            """,
            [{**r, "updated_at": now} for r in rows],
        )
    return len(rows)


def set_meta(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO universe_meta(key, value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_meta(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM universe_meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def _normalize_search(search: str | None) -> str | None:
    if not search:
        return None
    q = search.strip()
    if len(q) < 2:
        return None
    return q[:80]


def _symbol_filter_clauses(
    region: str = "all",
    asset_type: str | None = None,
    search: str | None = None,
    *,
    alias: str | None = None,
) -> tuple[list[str], list[Any]]:
    prefix = f"{alias}." if alias else ""
    clauses: list[str] = []
    params: list[Any] = []
    if region and region != "all":
        clauses.append(f"{prefix}region=?")
        params.append(region)
    if asset_type and asset_type != "all":
        clauses.append(f"{prefix}type=?")
        params.append(asset_type)
    q = _normalize_search(search)
    if q:
        pattern = f"%{q.lower()}%"
        clauses.append(
            f"("
            f"LOWER(COALESCE({prefix}name,'')) LIKE ? OR "
            f"LOWER(COALESCE({prefix}symbol,'')) LIKE ? OR "
            f"LOWER(COALESCE({prefix}yf_ticker,'')) LIKE ? OR "
            f"LOWER({prefix}id) LIKE ?"
            f")"
        )
        params.extend([pattern, pattern, pattern, pattern])
    return clauses, params


def get_symbols_page(
    page: int = 1,
    page_size: int = 50,
    region: str = "all",
    asset_type: str | None = None,
    sort: str = "buyability_desc",
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Pagina simboli; con sort analisi usa cache globale (non alfabetico per pagina)."""
    offset = max(0, (page - 1) * page_size)
    clauses, params = _symbol_filter_clauses(region, asset_type, search, alias="s")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    order_sql = _sort_order_sql(sort)
    params.extend([page_size, offset])

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT s.*
            FROM symbols s
            LEFT JOIN analysis_cache c ON c.symbol_id = s.id
            {where}
            ORDER BY {order_sql}, s.symbol COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def _sort_order_sql(sort: str) -> str:
    """Ordine SQL usando campi in analysis_cache (NULL = in fondo)."""
    # json_extract restituisce NULL se assente o cache mancante
    def num_field(path: str, null_rank: str = "-999999") -> str:
        return (
            f"CASE WHEN json_extract(c.data_json, '{path}') IS NULL "
            f"THEN {null_rank} ELSE CAST(json_extract(c.data_json, '{path}') AS REAL) END"
        )

    mapping: dict[str, str] = {
        "buyability_desc": f"{num_field('$.buyability_pct')} DESC",
        "buyability_asc": f"{num_field('$.buyability_pct', '999999')} ASC",
        "previsione_desc": f"{num_field('$.previsione_rendimento_pct')} DESC",
        "previsione_asc": f"{num_field('$.previsione_rendimento_pct', '999999')} ASC",
        "upside_desc": f"{num_field('$.analyst_upside_pct')} DESC",
        "prezzo_asc": f"{num_field('$.current_price', '999999999')} ASC",
        "prezzo_desc": f"{num_field('$.current_price')} DESC",
        "rendimento_desc": f"{num_field('$.rendimento_annuo_pct')} DESC",
        "ytd_desc": f"{num_field('$.ytd_pct')} DESC",
    }
    return mapping.get(sort, mapping["buyability_desc"])


def count_symbols(
    region: str | None = None,
    asset_type: str | None = None,
    search: str | None = None,
) -> int:
    clauses, params = _symbol_filter_clauses(
        region or "all",
        asset_type,
        search,
    )
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM symbols {where}", params).fetchone()
        return int(row["c"])


def count_by_region() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT region, COUNT(*) AS c FROM symbols GROUP BY region ORDER BY c DESC"
        ).fetchall()
        return {r["region"]: r["c"] for r in rows}


def count_by_type() -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT type, COUNT(*) AS c FROM symbols GROUP BY type ORDER BY c DESC"
        ).fetchall()
        return {r["type"]: r["c"] for r in rows}


def migrate_obbligazione_to_etf() -> int:
    """Legacy: obbligazioni erano ETF bond (BND/AGG)."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE symbols SET type='etf' WHERE type='obbligazione'")
        return cur.rowcount


def get_symbol_by_id(symbol_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM symbols WHERE id=?", (symbol_id,)).fetchone()
        return dict(row) if row else None


def get_cached_analysis(symbol_id: str, max_age_hours: int = 12) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT data_json, updated_at FROM analysis_cache WHERE symbol_id=?",
            (symbol_id,),
        ).fetchone()
        if not row:
            return None
        updated = datetime.fromisoformat(row["updated_at"])
        if datetime.utcnow() - updated > timedelta(hours=max_age_hours):
            return None
        data = json.loads(row["data_json"])
        # Invalida cache vecchia (modello buy/hold/sell o senza date analisti)
        if data.get("buyability_pct") is not None and (
            "analyst_buy_count" not in data
            or (
                not data.get("analyst_consensus_date")
                and not data.get("analyst_last_target_date")
                and not data.get("analyst_last_rating_date")
            )
        ):
            return None
        return data


def set_cached_analysis(symbol_id: str, data: dict[str, Any]) -> None:
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO analysis_cache(symbol_id, data_json, updated_at)
            VALUES(?,?,?)
            ON CONFLICT(symbol_id) DO UPDATE SET
                data_json=excluded.data_json, updated_at=excluded.updated_at
            """,
            (symbol_id, json.dumps(data, default=str), now),
        )


def search_startups_from_cache(limit: int = 20) -> list[dict[str, Any]]:
    """Return startup picks from cached analyses (best-effort)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT data_json FROM analysis_cache ORDER BY updated_at DESC LIMIT 5000"
        ).fetchall()
    results = [json.loads(r["data_json"]) for r in rows]
    return results[:limit]
