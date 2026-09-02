#!/usr/bin/env python3
"""SQLite: portafoglio multi-ticker + storico score nel tempo."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "stock_analysis.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS portfolio (
            ticker TEXT PRIMARY KEY,
            sector TEXT DEFAULT 'GENERICO',
            added_at TEXT NOT NULL,
            notes TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS score_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            ts TEXT NOT NULL,
            score REAL,
            verdict TEXT,
            buy_target REAL,
            price REAL,
            payload TEXT,
            FOREIGN KEY(ticker) REFERENCES portfolio(ticker)
        );
        CREATE INDEX IF NOT EXISTS idx_score_ticker_ts ON score_history(ticker, ts DESC);
        """
    )
    conn.commit()


def add_ticker(ticker: str, *, sector: str = "GENERICO", notes: str = "") -> None:
    ts = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO portfolio (ticker, sector, added_at, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET sector=excluded.sector, notes=excluded.notes
            """,
            (ticker.upper(), sector.upper(), ts, notes),
        )
        conn.commit()


def remove_ticker(ticker: str) -> bool:
    with _conn() as conn:
        cur = conn.execute("DELETE FROM portfolio WHERE ticker=?", (ticker.upper(),))
        conn.commit()
        return cur.rowcount > 0


def list_portfolio() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM portfolio ORDER BY ticker").fetchall()
    return [dict(r) for r in rows]


def save_score(ticker: str, analysis: dict[str, Any]) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    buy = analysis.get("buy_target_price")
    if buy is None and isinstance(analysis.get("buy_target_text"), str):
        import re

        m = re.search(r"\$(\d+(?:\.\d+)?)", analysis["buy_target_text"])
        if m:
            buy = float(m.group(1))
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO score_history (ticker, ts, score, verdict, buy_target, price, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker.upper(),
                ts,
                analysis.get("score"),
                analysis.get("verdict"),
                buy,
                analysis.get("price"),
                json.dumps(analysis, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()


def latest_score(ticker: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM score_history WHERE ticker=? ORDER BY ts DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None


def previous_score(ticker: str) -> dict[str, Any] | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM score_history WHERE ticker=? ORDER BY ts DESC LIMIT 1 OFFSET 1",
            (ticker.upper(),),
        ).fetchone()
    return dict(row) if row else None


def score_delta(ticker: str) -> float | None:
    cur = latest_score(ticker)
    prev = previous_score(ticker)
    if not cur or not prev:
        return None
    if cur.get("score") is None or prev.get("score") is None:
        return None
    return float(cur["score"]) - float(prev["score"])
