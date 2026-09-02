"""SQLite persistence for scores, watchlist, alert history."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_alert.env import ROOT

DB_PATH = ROOT / "data" / "quant_platform.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ticker_scores (
            ticker TEXT NOT NULL,
            ts TEXT NOT NULL,
            fundamental_score REAL,
            quant_score REAL,
            unified_score REAL,
            verdict TEXT,
            buy_target REAL,
            payload TEXT,
            PRIMARY KEY (ticker, ts)
        );
        CREATE TABLE IF NOT EXISTS dynamic_watchlist (
            ticker TEXT PRIMARY KEY,
            unified_score REAL,
            added_ts TEXT,
            source TEXT
        );
        CREATE TABLE IF NOT EXISTS alert_audit (
            alert_key TEXT PRIMARY KEY,
            ticker TEXT,
            ts TEXT,
            unified_score REAL,
            sent INTEGER
        );
        """
    )
    conn.commit()


def save_score(ticker: str, analysis: dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ticker_scores
            (ticker, ts, fundamental_score, quant_score, unified_score, verdict, buy_target, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(),
                ts,
                analysis.get("fundamental_score"),
                analysis.get("quant_score"),
                analysis.get("unified_score"),
                analysis.get("verdict"),
                analysis.get("buy_target_price"),
                json.dumps(analysis, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()


def upsert_watchlist(ticker: str, unified_score: float, source: str = "screener") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dynamic_watchlist (ticker, unified_score, added_ts, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                unified_score=excluded.unified_score,
                added_ts=excluded.added_ts,
                source=excluded.source
            """,
            (ticker.upper(), unified_score, ts, source),
        )
        conn.commit()


def get_dynamic_watchlist(min_score: float = 0.0) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ticker FROM dynamic_watchlist WHERE unified_score >= ? ORDER BY unified_score DESC",
            (min_score,),
        ).fetchall()
    return [str(r["ticker"]) for r in rows]


def record_alert(alert_key: str, ticker: str, unified_score: float, sent: bool) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO alert_audit (alert_key, ticker, ts, unified_score, sent)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert_key, ticker.upper(), ts, unified_score, 1 if sent else 0),
        )
        conn.commit()


def latest_scores(ticker: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM ticker_scores WHERE ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    if not row:
        return None
    return dict(row)
