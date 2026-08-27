"""Cruscotto locale: watchlist, ultimi prezzi, alert. Lo scan Telegram è il job CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_alert.aggregator import source_status
from finance_alert.config import load_config
from finance_alert.engine import LAST, run_scan
from finance_alert.env import load_env
from finance_alert.format import format_alerts
from finance_alert.telegram import load_credentials

st.set_page_config(page_title="Borsa Telegram alerts", layout="wide")
load_env()


def _last_scan() -> dict:
    if not LAST.is_file():
        return {}
    try:
        data = json.loads(LAST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


cfg = load_config()
status = source_status()
creds = load_credentials()
scan = _last_scan()
summary = scan.get("summary") or {}

st.title("Borsa — alert Telegram")
st.caption(
    "Modalità anticipo: setup utili, surprise, 8-K, gap pre/AH, peer fermi, catalizzatori. "
    "Non predice il salto; intercetta ciò che arriva prima o all’inizio."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Watchlist", len(cfg.symbols))
c2.metric("Prezzi ultimo scan", summary.get("n_quotes", "—"))
c3.metric("Alert nuovi", summary.get("n_new", "—"))
c4.metric("Telegram", "ok" if creds else "manca")

st.subheader("Fonti")
cols = st.columns(len(status))
for col, (name, ok) in zip(cols, status.items()):
    col.markdown(f"**{name}**")
    col.write("attiva" if ok else "no key / fallback")

if not status.get("finnhub"):
    st.info(
        "Finnhub non è configurato. In locale viene letto dal `.env` di "
        "Finance-Analyzer se esiste. Altrimenti registrati su finnhub.io "
        "e metti `FINNHUB_API_KEY` in `.env`. Yahoo chart resta disponibile senza chiave."
    )

left, right = st.columns((1.2, 1))
with left:
    st.subheader("Watchlist")
    rows = []
    quotes = scan.get("quotes") or {}
    for item in cfg.watchlist:
        q = quotes.get(item.ticker) or {}
        rows.append(
            {
                "ticker": item.ticker,
                "nome": item.name,
                "prezzo": q.get("price"),
                "var %": q.get("change_pct"),
                "sessione": q.get("session") or "regular",
                "fonte": q.get("source"),
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")

with right:
    st.subheader("Utili (ultimo scan)")
    earnings = scan.get("earnings") or []
    if earnings:
        st.dataframe(
            [
                {
                    "ticker": e.get("ticker"),
                    "data": e.get("date"),
                    "ora": e.get("hour"),
                    "EPS act": e.get("eps_actual"),
                    "EPS est": e.get("eps_estimate"),
                    "fonte": e.get("source"),
                }
                for e in earnings
            ],
            hide_index=True,
            width="stretch",
        )
    else:
        st.write("Nessun evento in finestra, oppure scan non ancora eseguito.")

st.subheader("Azioni")
with st.container(horizontal=True):
    run_scan_clicked = st.button(
        "Esegui scan (dry-run)",
        type="primary",
        icon=":material/play_arrow:",
    )
    show_text = st.button(
        "Testo Telegram ultimo scan",
        icon=":material/chat:",
    )

if run_scan_clicked:
    with st.spinner("Scan fonti in corso…"):
        result = run_scan()
    st.session_state["scan_summary"] = (
        f"Scan ok: {len(result.quotes)} prezzi, {len(result.fresh)} alert nuovi "
        f"su {len(result.alerts)} totali (non inviati)."
    )
    st.session_state["scan_text"] = (
        format_alerts(result.fresh, result.now) if result.fresh else "Nessun alert nuovo."
    )
    st.rerun()

if show_text:
    from finance_alert.models import Alert

    fresh = scan.get("fresh") or scan.get("alerts") or []
    if fresh:
        alerts = [
            Alert(
                key=a.get("key", ""),
                tipo=a.get("tipo", ""),
                ticker=a.get("ticker", ""),
                titolo=a.get("titolo", ""),
                body=a.get("body", ""),
                severity=a.get("severity") or "medium",
                url=a.get("url"),
            )
            for a in fresh
        ]
        st.session_state["scan_text"] = format_alerts(alerts)
    else:
        st.session_state["scan_text"] = "Nessun alert in cache."

if st.session_state.get("scan_summary"):
    st.success(st.session_state["scan_summary"])
if st.session_state.get("scan_text"):
    st.code(st.session_state["scan_text"], language=None)

st.subheader("Ultimi alert calcolati")
alerts = scan.get("alerts") or []
if alerts:
    st.dataframe(
        [
            {
                "tipo": a.get("tipo"),
                "ticker": a.get("ticker"),
                "titolo": a.get("titolo"),
                "severity": a.get("severity"),
            }
            for a in alerts
        ],
        hide_index=True,
        width="stretch",
    )
else:
    st.write("Esegui uno scan per vedere i candidati.")

st.caption(
    "Invio reale: `python -m finance_alert` oppure GitHub Actions. "
    "Questo cruscotto non manda messaggi da solo."
)
