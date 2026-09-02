#!/usr/bin/env python3
"""
Web app: ticker Yahoo (API) + HTML Investing/TIKR (+ fonti extra) → scoring locale.
"""
from __future__ import annotations

import os
import re
import traceback
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from scoring_engine import CRITICAL_FIELDS, run_analysis
from sectors import SECTORS, SECTOR_KEY_METRICS, SECTOR_LABELS, normalize_sector
from tikr_bundle import SLOT_INVESTING, SLOT_LABELS, classify_html
from yahoo_api import fetch_yahoo_metrics, normalize_ticker

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
ENV_FILE = ROOT / ".env"
NOT_AVAILABLE = "non disponibile"
MAX_SOURCE_CHARS = 500_000
MAX_HTML_FILES_PER_SLOT = 10  # max file .html per ogni box di upload
MAX_TIKR_DUMP_FILES = 25  # dump unico: Overview + tutte le tab insieme
MAX_TIKR_CHARS = 2_500_000
MAX_TIKR_FILE_CHARS = 900_000  # per singolo HTML TIKR (Cash Flow spesso in fondo)

# Tab TIKR mirate (priorità alta: FFO, CET1, NRR, NAV, growth…)
# Salva ogni tab con SingleFile dalla navigazione sinistra di TIKR.
TIKR_HTML_SOURCES = (
    {
        "id": "tikr",
        "label": "TIKR Overview",
        "hint": "Company overview / summary",
        "why": "Snapshot + metriche in evidenza",
        "url_hint": "tikr → Overview",
    },
    {
        "id": "tikr_financials",
        "label": "TIKR Financials",
        "hint": "Income / Balance / Cash Flow",
        "why": "FFO, AFFO, NII, FCF, ricavi, margini",
        "url_hint": "tikr → Financials (IS/BS/CF)",
    },
    {
        "id": "tikr_ratios",
        "label": "TIKR Ratios",
        "hint": "Ratios dentro Financials",
        "why": "CET1, ROE/ROA, D/E, Z-Score, NRR, NIM",
        "url_hint": "tikr → Financials → Ratios",
    },
    {
        "id": "tikr_valuation",
        "label": "TIKR Valuation",
        "hint": "Multiples + Street targets",
        "why": "P/FFO, NAV, EV/EBITDA, target prezzo",
        "url_hint": "tikr → Valuation",
    },
    {
        "id": "tikr_estimates",
        "label": "TIKR Estimates",
        "hint": "Consensus / CAGR forward",
        "why": "Growth, EPS fwd, revisioni analisti",
        "url_hint": "tikr → Estimates",
    },
    {
        "id": "tikr_segments",
        "label": "TIKR Segments",
        "hint": "Segmenti / geografie / prodotti",
        "why": "SS NOI, ARPU, mix ricavi",
        "url_hint": "tikr → Segments",
    },
    {
        "id": "tikr_ownership",
        "label": "TIKR Ownership",
        "hint": "Istituzionali / insider",
        "why": "Ownership, short, insider activity",
        "url_hint": "tikr → Ownership",
    },
    {
        "id": "tikr_competitors",
        "label": "TIKR Competitors",
        "hint": "Peer comps",
        "why": "Confronto multipli e margini peer",
        "url_hint": "tikr → Competitors",
    },
    {
        "id": "tikr_earnings",
        "label": "TIKR Earnings",
        "hint": "Beats / misses / surprise",
        "why": "Earnings surprise, guidance",
        "url_hint": "tikr → Earnings",
    },
    {
        "id": "tikr_other",
        "label": "TIKR Altro",
        "hint": "Altre pagine TIKR (max 10 file)",
        "why": "Filings, chart, custom views…",
        "url_hint": "tikr → qualsiasi altra tab",
    },
)

# Altre fonti HTML (priorità bassa → riempiono i buchi)
EXTRA_HTML_SOURCES = (
    {
        "id": "finviz",
        "label": "Finviz",
        "hint": "Quote / snapshot SingleFile",
        "url_hint": "finviz.com/quote.ashx?t=TICKER",
    },
    {
        "id": "marketwatch",
        "label": "MarketWatch",
        "hint": "Overview / profile SingleFile",
        "url_hint": "marketwatch.com/investing/stock/TICKER",
    },
    {
        "id": "gurufocus",
        "label": "GuruFocus",
        "hint": "Summary / financials SingleFile",
        "url_hint": "gurufocus.com/stock/TICKER/summary",
    },
    {
        "id": "tipranks",
        "label": "TipRanks",
        "hint": "Analyst forecasts SingleFile",
        "url_hint": "tipranks.com/stocks/TICKER/forecast",
    },
    {
        "id": "morningstar",
        "label": "Morningstar",
        "hint": "Quote / valuation SingleFile",
        "url_hint": "morningstar.com/stocks/.../TICKER",
    },
)

app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024  # ~120 MB per molte SingleFile


def load_dotenv(path: Path = ENV_FILE) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


# Sezioni da NON perdere quando l'HTML SingleFile è enorme
_PRIORITY_SECTION_RES = (
    re.compile(
        r"(?is)((?:Consolidated\s+)?(?:Cash Flow Statement|Statement of Cash Flows|"
        r"Cash Flows? Statement|Cash Flow)\b.{0,100000})",
    ),
    re.compile(
        r"(?is)((?:Free Cash Flow|Cash From Operations|Cash from Operating Activities|"
        r"Operating Cash Flow|Capital Expenditur[es]*|Purchase[s]? of Property).{0,20000})",
    ),
    re.compile(
        r"(?is)((?:Estimates|Analyst Estimates|Financial Estimates|Forward Estimates)\b.{0,80000})",
    ),
)


def _extract_priority_chunks(text: str) -> str:
    """Estrae Cash Flow / Estimates / FCF prima del troncamento."""
    chunks: list[str] = []
    seen: set[str] = set()
    for cre in _PRIORITY_SECTION_RES:
        for m in cre.finditer(text):
            piece = m.group(1).strip()
            key = piece[:180].lower()
            if key in seen or len(piece) < 40:
                continue
            seen.add(key)
            chunks.append(piece)
            if len(chunks) >= 8:
                break
        if len(chunks) >= 8:
            break
    return "\n\n".join(chunks)


def compact_html(raw: str, max_chars: int = MAX_SOURCE_CHARS) -> str:
    text = raw
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table|section|td|th)>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"), ("&quot;", '"')):
        text = text.replace(a, b)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    priority = _extract_priority_chunks(text)
    if priority:
        # Cash Flow / Estimates in testa così restano anche se il body viene tagliato
        rest_budget = max(0, max_chars - len(priority) - 80)
        body = text if len(text) <= rest_budget else text[:rest_budget]
        text = (
            "=== PRIORITY: CASH FLOW / ESTIMATES ===\n"
            + priority
            + "\n=== END PRIORITY ===\n\n"
            + body
        )
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n[... TRONCATO a {max_chars} caratteri ...]"
    return text


def read_one(file_storage, max_chars: int = MAX_SOURCE_CHARS) -> str | None:
    if file_storage is None or not getattr(file_storage, "filename", None):
        return None
    raw = file_storage.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="replace")
    content = content.strip()
    if not content:
        return None
    name = file_storage.filename.lower()
    if name.endswith((".html", ".htm")) or "<html" in content[:2000].lower():
        return compact_html(content, max_chars=max_chars)
    return content[:max_chars]


def _valid_uploads(files, max_n: int | None = None) -> list:
    """Solo file con nome, max MAX_HTML_FILES_PER_SLOT (o max_n)."""
    limit = MAX_HTML_FILES_PER_SLOT if max_n is None else max_n
    out = []
    for f in files or []:
        if getattr(f, "filename", None):
            out.append(f)
        if len(out) >= limit:
            break
    return out


def read_many(files, max_chars: int = MAX_SOURCE_CHARS, per_file_chars: int | None = None) -> str | None:
    """Unisce più HTML della stessa fonte (max 10 file per slot)."""
    files = _valid_uploads(files)
    if not files:
        return None
    file_limit = per_file_chars or max_chars
    parts: list[str] = []
    for f in files:
        text = read_one(f, max_chars=file_limit)
        if text:
            parts.append(f"--- FILE: {f.filename} ---\n{text}")
    if not parts:
        return None
    merged = "\n\n".join(parts)
    if len(merged) > max_chars:
        # Riprova a tenere i chunk PRIORITY anche nel merge troncato
        prio = _extract_priority_chunks(merged)
        if prio:
            budget = max(0, max_chars - len(prio) - 60)
            merged = (
                "=== PRIORITY: CASH FLOW / ESTIMATES ===\n"
                + prio[: max_chars // 2]
                + "\n=== END PRIORITY ===\n\n"
                + merged[:budget]
            )
        else:
            merged = merged[:max_chars]
        merged += "\n\n[... TRONCATO ...]"
    return merged


def enforce_file_limits() -> str | None:
    """Ritorna messaggio errore se uno slot supera i limiti."""
    fields = ["investing"] + [s["id"] for s in TIKR_HTML_SOURCES] + [s["id"] for s in EXTRA_HTML_SOURCES]
    for field in fields:
        n = sum(1 for f in request.files.getlist(field) if getattr(f, "filename", None))
        if n > MAX_HTML_FILES_PER_SLOT:
            return f"Troppi file in '{field}': {n} (max {MAX_HTML_FILES_PER_SLOT} per slot)"
    n_dump = sum(1 for f in request.files.getlist("tikr_auto") if getattr(f, "filename", None))
    if n_dump > MAX_TIKR_DUMP_FILES:
        return f"Troppi file nel dump TIKR: {n_dump} (max {MAX_TIKR_DUMP_FILES})"
    return None


def read_storage_raw(file_storage) -> tuple[str, str] | None:
    """Nome file + testo grezzo (prima del compact)."""
    if file_storage is None or not getattr(file_storage, "filename", None):
        return None
    raw = file_storage.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1", errors="replace")
    content = content.strip()
    if not content:
        return None
    return file_storage.filename, content


def ingest_tikr_dump(files) -> tuple[dict[str, list[tuple[str, str]]], list[dict]]:
    """
    Classifica un dump di HTML SingleFile (URL in testa al file).
    Ritorna: slot → [(filename, testo compact)], lista meta per la UI.
    """
    grouped: dict[str, list[tuple[str, str]]] = {}
    meta: list[dict] = []
    for f in _valid_uploads(files, max_n=MAX_TIKR_DUMP_FILES):
        pair = read_storage_raw(f)
        if not pair:
            continue
        filename, raw = pair
        item = classify_html(raw, filename)
        is_html = filename.lower().endswith((".html", ".htm")) or "<html" in raw[:2000].lower()
        limit = MAX_TIKR_FILE_CHARS if item.slot.startswith("tikr") else MAX_SOURCE_CHARS
        text = compact_html(raw, max_chars=limit) if is_html else raw[:limit]
        grouped.setdefault(item.slot, []).append((filename, text))
        meta.append(
            {
                "file": filename,
                "slot": item.slot,
                "label": SLOT_LABELS.get(item.slot, item.slot),
                "detail": item.detail,
                "url": item.url,
            }
        )
    return grouped, meta


def _join_named_parts(parts: list[tuple[str, str]], max_chars: int) -> str | None:
    if not parts:
        return None
    chunks = [f"--- FILE: {name} ---\n{text}" for name, text in parts]
    merged = "\n\n".join(chunks)
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "\n\n[... TRONCATO ...]"
    return merged


def merge_labeled_parts(
    labeled: list[tuple[str, str]],
    max_chars: int = MAX_SOURCE_CHARS,
) -> str | None:
    """Unisce blocchi etichettati (es. tab TIKR diverse)."""
    if not labeled:
        return None
    chunks = [f"=== {label} ===\n{text}" for label, text in labeled]
    merged = "\n\n".join(chunks)
    if len(merged) > max_chars:
        merged = merged[:max_chars] + "\n\n[... TRONCATO ...]"
    return merged


@app.get("/")
def index():
    return render_template(
        "index.html",
        sectors=SECTORS,
        sector_labels=SECTOR_LABELS,
        sector_metrics=SECTOR_KEY_METRICS,
        critical=CRITICAL_FIELDS,
        tikr_sources=TIKR_HTML_SOURCES,
        extra_sources=EXTRA_HTML_SOURCES,
        max_html_files=MAX_HTML_FILES_PER_SLOT,
        max_tikr_dump=MAX_TIKR_DUMP_FILES,
    )


@app.post("/api/analyze")
def analyze():
    try:
        try:
            sector = normalize_sector(request.form.get("sector") or "")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        try:
            ticker = normalize_ticker(request.form.get("ticker") or "")
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        limit_err = enforce_file_limits()
        if limit_err:
            return jsonify({"ok": False, "error": limit_err}), 400

        dump_grouped, dump_meta = ingest_tikr_dump(request.files.getlist("tikr_auto"))

        investing = read_many(request.files.getlist("investing"))
        if not investing:
            investing = _join_named_parts(dump_grouped.get(SLOT_INVESTING, []), MAX_SOURCE_CHARS)
        if not investing:
            return jsonify({"ok": False, "error": "Carica almeno 1 file Investing.com (.html)"}), 400

        tikr_parts: list[tuple[str, str]] = []
        tikr_meta: dict[str, dict] = {}
        for src in TIKR_HTML_SOURCES:
            sid = src["id"]
            text = read_many(
                request.files.getlist(sid),
                max_chars=MAX_TIKR_FILE_CHARS,
                per_file_chars=MAX_TIKR_FILE_CHARS,
            )
            auto_parts = dump_grouped.get(sid, [])
            if auto_parts:
                auto_text = _join_named_parts(auto_parts, MAX_TIKR_FILE_CHARS)
                if auto_text:
                    text = f"{text}\n\n{auto_text}" if text else auto_text
                    if len(text) > MAX_TIKR_FILE_CHARS:
                        text = text[:MAX_TIKR_FILE_CHARS] + "\n\n[... TRONCATO ...]"
            if text:
                tikr_parts.append((src["label"], text))
                tikr_meta[sid] = {"ok": True, "chars": len(text), "label": src["label"]}
            else:
                tikr_meta[sid] = {"ok": False, "chars": 0, "label": src["label"]}

        tikr = merge_labeled_parts(tikr_parts, max_chars=MAX_TIKR_CHARS) or NOT_AVAILABLE
        # Dopo merge multi-tab, ripristina sezioni CF/Estimates in testa
        if tikr != NOT_AVAILABLE:
            prio = _extract_priority_chunks(tikr)
            if prio and "=== PRIORITY:" not in tikr[:200]:
                tikr = (
                    "=== PRIORITY: CASH FLOW / ESTIMATES ===\n"
                    + prio
                    + "\n=== END PRIORITY ===\n\n"
                    + tikr
                )
                if len(tikr) > MAX_TIKR_CHARS:
                    tikr = tikr[:MAX_TIKR_CHARS] + "\n\n[... TRONCATO ...]"

        extra_sources: dict[str, str] = {}
        extra_meta: dict[str, dict] = {}
        for src in EXTRA_HTML_SOURCES:
            sid = src["id"]
            text = read_many(request.files.getlist(sid))
            if text:
                extra_sources[sid] = text
                extra_meta[sid] = {"ok": True, "chars": len(text)}
            else:
                extra_meta[sid] = {"ok": False, "chars": 0}

        try:
            yahoo_metrics = fetch_yahoo_metrics(ticker)
        except (ValueError, RuntimeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        result = run_analysis(
            investing,
            tikr,
            sector,
            yahoo_metrics=yahoo_metrics,
            extra_sources=extra_sources or None,
        )
        report = result["report"]

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = OUTPUT_DIR / f"report_{sector.lower()}_{stamp}.txt"
        out_path.write_text(report, encoding="utf-8")

        filled = sum(1 for k, v in yahoo_metrics.items() if not k.startswith("_") and v is not None)
        tikr_loaded = [sid for sid, meta in tikr_meta.items() if meta["ok"]]

        return jsonify(
            {
                "ok": True,
                "sector": sector,
                "ticker": ticker,
                "report": report,
                "score": result["score"],
                "verdict": result["verdict"],
                "risk": result["risk"],
                "reliable": result["reliable"],
                "coverage": result["coverage"],
                "saved_as": str(out_path),
                "key_metrics": SECTOR_KEY_METRICS.get(sector, []),
                "sources": {
                    "investing_chars": len(investing),
                    "yahoo": True,
                    "yahoo_fields": filled,
                    "tikr": bool(tikr_loaded),
                    "tikr_chars": 0 if tikr == NOT_AVAILABLE else len(tikr),
                    "tikr_tabs": tikr_meta,
                    "tikr_loaded": tikr_loaded,
                    "tikr_auto_map": dump_meta,
                    "extra": extra_meta,
                    "extra_loaded": list(extra_sources.keys()),
                },
                "smart_money_bonus": result.get("smart_money_bonus", 0),
                "base_score": result.get("base_score", result["score"]),
            }
        )
    except Exception as exc:
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/auto-analyze/<ticker>", methods=["GET"])
def api_auto_analyze(ticker: str):
    """Analisi solo Yahoo API — niente HTML (scoring automatico)."""
    from auto_analyze import analyze_auto

    sector = request.args.get("sector")
    try:
        analysis = analyze_auto(ticker, sector=sector)
        return jsonify({"ok": True, **analysis})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/portfolio", methods=["GET", "POST", "DELETE"])
def api_portfolio():
    """Portafoglio persistente multi-ticker (SQLite)."""
    from portfolio_db import add_ticker, list_portfolio, remove_ticker

    if request.method == "GET":
        return jsonify({"ok": True, "portfolio": list_portfolio()})
    data = request.get_json(silent=True) or {}
    ticker = (data.get("ticker") or request.args.get("ticker") or "").strip().upper()
    if not ticker:
        return jsonify({"ok": False, "error": "ticker obbligatorio"}), 400
    if request.method == "POST":
        add_ticker(ticker, sector=data.get("sector") or "GENERICO", notes=data.get("notes") or "")
        return jsonify({"ok": True, "added": ticker})
    removed = remove_ticker(ticker)
    return jsonify({"ok": removed, "removed": ticker if removed else None})


@app.route("/api/portfolio/scan", methods=["POST"])
def api_portfolio_scan():
    """Ricalcola score portafoglio + alert Telegram su variazioni."""
    from auto_analyze import scan_portfolio

    notify = request.args.get("notify", "1") != "0"
    results = scan_portfolio(notify=notify)
    return jsonify({"ok": True, "results": results})


def main() -> int:
    port = int(os.getenv("PORT", "5055"))
    print("=" * 56)
    print("  Stock Analysis - Yahoo + Investing + TIKR tabs")
    print(f"  http://127.0.0.1:{port}")
    print(f"  TIKR dump: max {MAX_TIKR_DUMP_FILES} HTML (auto-classifica dalle URL SingleFile)")
    print("=" * 56)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
