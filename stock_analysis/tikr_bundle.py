#!/usr/bin/env python3
"""
Smista HTML SingleFile TIKR/Investing senza assegnare a mano ogni tab.

SingleFile salva in testa:
  url: https://app.tikr.com/stock/financials?...&tab=cf

Da un file Overview (o da una cartella) trova i gemelli dello stesso titolo
e li classifica: Financials, Ratios, Valuation, Estimates, Ownership, …

Uso:
  python tikr_bundle.py --overview "C:\\Users\\...\\TIKR Terminal (...).html"
  python tikr_bundle.py --overview FILE.html --ticker CSAN --sector ENERGY
  python tikr_bundle.py --folder "C:\\Users\\...\\Downloads" --ticker CSAN
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HEAD_BYTES = 24_000

# Slot allineati a TIKR_HTML_SOURCES in app.py
SLOT_TIKR = "tikr"
SLOT_FINANCIALS = "tikr_financials"
SLOT_RATIOS = "tikr_ratios"
SLOT_VALUATION = "tikr_valuation"
SLOT_ESTIMATES = "tikr_estimates"
SLOT_SEGMENTS = "tikr_segments"
SLOT_OWNERSHIP = "tikr_ownership"
SLOT_COMPETITORS = "tikr_competitors"
SLOT_EARNINGS = "tikr_earnings"
SLOT_OTHER = "tikr_other"
SLOT_INVESTING = "investing"

SLOT_LABELS = {
    SLOT_TIKR: "TIKR Overview",
    SLOT_FINANCIALS: "TIKR Financials",
    SLOT_RATIOS: "TIKR Ratios",
    SLOT_VALUATION: "TIKR Valuation",
    SLOT_ESTIMATES: "TIKR Estimates",
    SLOT_SEGMENTS: "TIKR Segments",
    SLOT_OWNERSHIP: "TIKR Ownership",
    SLOT_COMPETITORS: "TIKR Competitors",
    SLOT_EARNINGS: "TIKR Earnings",
    SLOT_OTHER: "TIKR Altro",
    SLOT_INVESTING: "Investing.com",
}

SAVED_URL_RE = re.compile(r"(?im)^\s*url:\s*(\S+)")
TICKER_IN_NAME_RE = re.compile(r"\(([A-Z]{1,6}(?:[.\-][A-Z0-9]{1,5})?)\)")
CID_RE = re.compile(r"[?&]cid=(\d+)", re.I)
TID_RE = re.compile(r"[?&]tid=(\d+)", re.I)
TITLE_TICKER_RE = re.compile(
    r"\(([A-Z]{1,6}(?:[.\-][A-Z0-9]{1,5})?)\)\s*[-–—]\s*TIKR",
    re.I,
)

FINANCIALS_TABS = {
    "is": "Income Statement",
    "bs": "Balance Sheet",
    "cf": "Cash Flow",
    "r": "Ratios",
    "ratios": "Ratios",
    "seg": "Segments",
    "segments": "Segments",
}


@dataclass
class ClassifiedFile:
    path: Path | None
    filename: str
    slot: str
    detail: str
    url: str
    cid: str = ""
    ticker_guess: str = ""


@dataclass
class Bundle:
    ticker: str = ""
    cid: str = ""
    overview: Path | None = None
    files: list[ClassifiedFile] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)

    def by_slot(self) -> dict[str, list[ClassifiedFile]]:
        out: dict[str, list[ClassifiedFile]] = {}
        for item in self.files:
            out.setdefault(item.slot, []).append(item)
        return out


def read_head(path: Path, nbytes: int = HEAD_BYTES) -> str:
    with path.open("rb") as fh:
        raw = fh.read(nbytes)
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_saved_url(text: str) -> str:
    """URL originale SingleFile (prime righe) oppure primo link app.tikr.com/stock/."""
    m = SAVED_URL_RE.search(text[:8000] if len(text) > 8000 else text)
    if m:
        return m.group(1).strip().rstrip("-->").strip()
    m = re.search(
        r"https://app\.tikr\.com/stock/[a-z]+(?:\?[^\s\"'<>]*)?",
        text[:12000],
        re.I,
    )
    return m.group(0) if m else ""


def ticker_from_filename(name: str) -> str:
    m = TICKER_IN_NAME_RE.search(name)
    return (m.group(1) if m else "").upper()


def ticker_from_html(text: str) -> str:
    m = TITLE_TICKER_RE.search(text[:4000])
    if m:
        return m.group(1).upper()
    m = TICKER_IN_NAME_RE.search(text[:4000])
    return (m.group(1) if m else "").upper()


def cid_from_text(text: str) -> str:
    m = CID_RE.search(text[:8000])
    return m.group(1) if m else ""


def classify_tikr_url(url: str) -> tuple[str, str]:
    """Ritorna (slot_id, dettaglio tab)."""
    if not url:
        return SLOT_OTHER, "sconosciuto"
    low = url.lower()
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    tab = (parse_qs(parsed.query).get("tab") or [""])[0].lower()

    if "investing.com" in low:
        return SLOT_INVESTING, "Investing.com"
    if "finviz.com" in low:
        return SLOT_OTHER, "Finviz"
    if "tikr.com" not in low:
        if "quotazione" in low or "equities" in low:
            return SLOT_INVESTING, "Investing.com"
        return SLOT_OTHER, path or "altro"

    if path.endswith("/about") or "/stock/about" in path:
        return SLOT_TIKR, "Overview"
    if "/stock/financials" in path:
        if tab in ("r", "ratios", "ratio"):
            return SLOT_RATIOS, "Ratios"
        if tab in ("seg", "segments", "segment"):
            return SLOT_SEGMENTS, "Segments"
        detail = FINANCIALS_TABS.get(tab, "Financials")
        return SLOT_FINANCIALS, detail
    if "/stock/multiples" in path or "/stock/valuation" in path:
        if tab in ("comp", "comps", "peers", "peer"):
            return SLOT_COMPETITORS, "Competitors / comps"
        if tab in ("street",):
            return SLOT_VALUATION, "Street targets"
        return SLOT_VALUATION, "Multiples" if tab in ("multi", "multiples", "") else tab
    if "/stock/estimates" in path:
        if tab in ("earn", "earnings", "surprise"):
            return SLOT_EARNINGS, "Earnings surprise"
        return SLOT_ESTIMATES, "Estimates"
    if "/stock/ownership" in path:
        return SLOT_OWNERSHIP, "Ownership"
    if "/stock/earnings" in path:
        return SLOT_EARNINGS, "Earnings"
    if "/stock/segments" in path:
        return SLOT_SEGMENTS, "Segments"
    if "/stock/transcripts" in path:
        return SLOT_EARNINGS, "Transcripts"
    if any(x in path for x in ("/stock/filings", "/stock/models", "/stock/chart")):
        return SLOT_OTHER, path.rsplit("/", 1)[-1]
    return SLOT_OTHER, path.rsplit("/", 1)[-1] or "Altro"


def classify_html(text: str, filename: str = "") -> ClassifiedFile:
    url = extract_saved_url(text)
    name_l = filename.lower()
    if not url:
        if "investing" in name_l or "quotazione" in name_l:
            slot, detail = SLOT_INVESTING, "Investing.com (nome file)"
        elif "tikr" in name_l:
            slot, detail = SLOT_OTHER, "TIKR (URL mancante)"
        else:
            slot, detail = SLOT_OTHER, "sconosciuto"
    else:
        slot, detail = classify_tikr_url(url)
        if slot == SLOT_OTHER and ("investing" in name_l or "quotazione" in name_l):
            slot, detail = SLOT_INVESTING, "Investing.com"

    return ClassifiedFile(
        path=None,
        filename=filename,
        slot=slot,
        detail=detail,
        url=url,
        cid=cid_from_text(url or text),
        ticker_guess=ticker_from_filename(filename) or ticker_from_html(text),
    )


def classify_path(path: Path) -> ClassifiedFile:
    item = classify_html(read_head(path), path.name)
    item.path = path
    return item


def _is_html(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in {".html", ".htm"}


def discover_from_overview(overview: Path, extra_files: list[Path] | None = None) -> Bundle:
    """Parte dall'Overview e raccoglie i SingleFile gemelli nella stessa cartella."""
    overview = overview.expanduser().resolve()
    if not overview.is_file():
        raise FileNotFoundError(f"Overview non trovato: {overview}")

    head = read_head(overview)
    ov = classify_html(head, overview.name)
    ov.path = overview
    ticker = ov.ticker_guess
    cid = ov.cid

    folder = overview.parent
    candidates: dict[str, Path] = {str(overview): overview}
    for p in folder.iterdir():
        if _is_html(p):
            candidates[str(p.resolve())] = p.resolve()
    for p in extra_files or []:
        rp = Path(p).expanduser().resolve()
        if _is_html(rp):
            candidates[str(rp)] = rp

    bundle = Bundle(ticker=ticker, cid=cid, overview=overview)
    seen_keys: set[tuple[str, str]] = set()

    for path in sorted(candidates.values(), key=lambda x: x.stat().st_mtime):
        item = classify_path(path)
        same_ticker = bool(ticker) and (
            ticker == item.ticker_guess
            or f"({ticker})" in path.name.upper()
            or re.search(rf"\b{re.escape(ticker)}\b", path.name, re.I)
        )
        same_cid = bool(cid) and item.cid == cid
        is_investing = item.slot == SLOT_INVESTING and same_ticker
        is_tikr = item.slot.startswith("tikr") and (same_cid or same_ticker or "tikr" in path.name.lower())

        # Overview: sempre incluso. Altri: stesso titolo TIKR oppure Investing dello stesso ticker.
        if path.resolve() != overview.resolve() and not (is_tikr or is_investing):
            continue
        if path.resolve() != overview.resolve() and item.slot.startswith("tikr") and cid and item.cid and item.cid != cid:
            continue

        key = (item.slot, item.detail, item.url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        bundle.files.append(item)

    if not any(f.path and f.path.resolve() == overview.resolve() for f in bundle.files):
        bundle.files.insert(0, ov)

    present = {f.slot for f in bundle.files}
    useful = [
        SLOT_TIKR,
        SLOT_FINANCIALS,
        SLOT_RATIOS,
        SLOT_VALUATION,
        SLOT_ESTIMATES,
        SLOT_OWNERSHIP,
        SLOT_INVESTING,
    ]
    bundle.missing_slots = [s for s in useful if s not in present]
    return bundle


def discover_folder(folder: Path, ticker: str = "") -> Bundle:
    folder = folder.expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Cartella non trovata: {folder}")
    htmls = [p for p in folder.iterdir() if _is_html(p)]
    overview = None
    for p in htmls:
        item = classify_path(p)
        if item.slot == SLOT_TIKR and (not ticker or item.ticker_guess == ticker.upper() or ticker.upper() in p.name.upper()):
            overview = p
            break
    if overview is None and htmls:
        # fallback: file TIKR più vecchio / primo about
        overview = htmls[0]
    if overview is None:
        return Bundle(ticker=ticker.upper())
    return discover_from_overview(overview)


def format_mapping(bundle: Bundle) -> str:
    lines = []
    if bundle.ticker:
        lines.append(f"Ticker: {bundle.ticker}")
    if bundle.cid:
        lines.append(f"TIKR cid: {bundle.cid}")
    if bundle.overview:
        lines.append(f"Overview: {bundle.overview.name}")
    lines.append(f"File classificati: {len(bundle.files)}")
    lines.append("")
    by = bundle.by_slot()
    order = list(SLOT_LABELS.keys())
    for slot in order:
        items = by.get(slot) or []
        if not items:
            continue
        lines.append(f"[{SLOT_LABELS.get(slot, slot)}]")
        for it in items:
            name = it.filename
            extra = f" — {it.detail}" if it.detail else ""
            lines.append(f"  • {name}{extra}")
            if it.url:
                lines.append(f"    {it.url}")
        lines.append("")
    if bundle.missing_slots:
        miss = ", ".join(SLOT_LABELS.get(s, s) for s in bundle.missing_slots)
        lines.append(f"Mancanti (utili): {miss}")
    return "\n".join(lines).strip() + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Classifica HTML TIKR SingleFile partendo dall'Overview (niente copia-incolla per tab).",
    )
    p.add_argument(
        "overview_pos",
        nargs="?",
        help="Percorso Overview TIKR (alternativa a --overview).",
    )
    p.add_argument(
        "--overview", "-o",
        help="File HTML Overview TIKR (SingleFile). Cerca i gemelli nella stessa cartella.",
    )
    p.add_argument(
        "--folder", "-f",
        help="Cartella con tutti gli HTML (alternativa a --overview).",
    )
    p.add_argument(
        "--ticker", "-t",
        help="Ticker Yahoo (se omesso: letto dal nome/titolo Overview).",
    )
    p.add_argument(
        "--sector", "-s",
        help="Settore per lo scoring (es. ENERGY, GENERICO). Se presente, lancia l'analisi.",
    )
    p.add_argument(
        "--investing", "-i",
        help="HTML Investing.com (se omesso: cerca nella stessa cartella dell'Overview).",
    )
    p.add_argument(
        "--list-only",
        action="store_true",
        help="Mostra solo lo smistamento, non lanciare lo scoring.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    args = parse_args(argv)
    overview = args.overview or args.overview_pos
    extra = [Path(args.investing)] if args.investing else []

    if overview:
        bundle = discover_from_overview(Path(overview), extra_files=extra)
    elif args.folder:
        bundle = discover_folder(Path(args.folder), ticker=args.ticker or "")
    else:
        print("Errore: specifica l'Overview (argomento o --overview) oppure --folder CARTELLA", file=sys.stderr)
        return 1

    if args.ticker:
        bundle.ticker = args.ticker.strip().upper()

    print(format_mapping(bundle))

    if args.list_only or not args.sector:
        if not args.sector and not args.list_only:
            print("Per lo scoring: aggiungi --sector ENERGY (o GENERICO, …) --ticker CSAN")
        return 0

    # Import tardivo: evita ciclo con app.py
    from app import (  # noqa: WPS433
        MAX_TIKR_CHARS,
        MAX_TIKR_FILE_CHARS,
        NOT_AVAILABLE,
        OUTPUT_DIR,
        TIKR_HTML_SOURCES,
        compact_html,
        merge_labeled_parts,
    )
    from scoring_engine import run_analysis
    from sectors import normalize_sector
    from yahoo_api import fetch_yahoo_metrics, normalize_ticker

    ticker = normalize_ticker(bundle.ticker or args.ticker or "")
    sector = normalize_sector(args.sector)

    def load_compact(path: Path, limit: int) -> str:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return compact_html(raw, max_chars=limit)

    investing_parts: list[str] = []
    tikr_groups: dict[str, list[str]] = {}
    slot_to_label = {s["id"]: s["label"] for s in TIKR_HTML_SOURCES}

    for item in bundle.files:
        if not item.path:
            continue
        if item.slot == SLOT_INVESTING:
            investing_parts.append(
                f"--- FILE: {item.filename} ---\n{load_compact(item.path, 500_000)}"
            )
            continue
        label = slot_to_label.get(item.slot, SLOT_LABELS.get(item.slot, item.slot))
        text = load_compact(item.path, MAX_TIKR_FILE_CHARS)
        tikr_groups.setdefault(label, []).append(
            f"--- FILE: {item.filename} ({item.detail}) ---\n{text}"
        )

    if not investing_parts:
        print("Errore: Investing.com non trovato nella cartella. Passa --investing FILE.html", file=sys.stderr)
        return 1

    investing = "\n\n".join(investing_parts)
    tikr_parts = [(lab, "\n\n".join(chunks)) for lab, chunks in tikr_groups.items()]
    tikr = merge_labeled_parts(tikr_parts, max_chars=MAX_TIKR_CHARS) or NOT_AVAILABLE

    print(f"Yahoo API: {ticker} …")
    yahoo_metrics = fetch_yahoo_metrics(ticker)
    result = run_analysis(investing, tikr, sector, yahoo_metrics=yahoo_metrics)
    report = result["report"]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"report_{sector.lower()}_{stamp}.txt"
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport: {out_path}")
    print(f"Verdict: {result['verdict']}  {result['score']:.0f}/100  rischio {result['risk']}/5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
