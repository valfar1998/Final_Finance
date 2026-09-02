"""Portfolio tracking + score history for Finance Analyzer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from services.cache_db import get_conn


def _init_portfolio_tables() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS user_portfolio (
                ticker TEXT PRIMARY KEY,
                yf_ticker TEXT NOT NULL,
                name TEXT,
                added_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS score_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                ts TEXT NOT NULL,
                buyability_pct REAL,
                previsione_rendimento_pct REAL,
                current_price REAL,
                analyst_target REAL,
                payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fa_score_ts ON score_history(ticker, ts DESC);
            """
        )


def add_to_portfolio(ticker: str, *, yf_ticker: str | None = None, name: str = "") -> None:
    _init_portfolio_tables()
    ts = datetime.now(timezone.utc).isoformat()
    yf = (yf_ticker or ticker).upper()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_portfolio (ticker, yf_ticker, name, added_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET yf_ticker=excluded.yf_ticker, name=excluded.name
            """,
            (ticker.upper(), yf, name, ts),
        )


def remove_from_portfolio(ticker: str) -> bool:
    _init_portfolio_tables()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM user_portfolio WHERE ticker=?", (ticker.upper(),))
        return cur.rowcount > 0


def list_portfolio() -> list[dict[str, Any]]:
    _init_portfolio_tables()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM user_portfolio ORDER BY ticker").fetchall()
    return [dict(r) for r in rows]


def record_score_snapshot(ticker: str, analysis: dict[str, Any]) -> None:
    _init_portfolio_tables()
    ts = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO score_history
            (ticker, ts, buyability_pct, previsione_rendimento_pct, current_price, analyst_target, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(),
                ts,
                analysis.get("buyability_pct"),
                analysis.get("previsione_rendimento_pct"),
                analysis.get("current_price"),
                analysis.get("analyst_target_mean"),
                json.dumps(analysis, default=str),
            ),
        )


def latest_snapshot(ticker: str) -> dict[str, Any] | None:
    _init_portfolio_tables()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM score_history WHERE ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None


def previous_snapshot(ticker: str) -> dict[str, Any] | None:
    _init_portfolio_tables()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM score_history WHERE ticker=? ORDER BY ts DESC LIMIT 1 OFFSET 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None
