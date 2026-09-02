#!/usr/bin/env python3
"""
Genera il prompt completo per l'analisi azionaria unificata.

Accetta (per ogni fonte):
  - file SingleFile / HTML / TXT (consigliato)
  - URL della pagina (tentativo di download; spesso bloccato dai siti)
  - "non disponibile"
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPT_FILE = ROOT / "PROMPT_UNIFICATO.txt"
OUTPUT_DIR = ROOT / "output"
INPUT_DIR = ROOT / "input"

from sectors import SECTORS, normalize_sector as _normalize_sector

NOT_AVAILABLE = "non disponibile"
URL_RE = re.compile(r"^https?://", re.I)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)


def is_url(value: str) -> bool:
    return bool(URL_RE.match(value.strip()))


def fetch_url(url: str, timeout: int = 30) -> str:
    """Scarica una pagina. Molti siti (Investing, Yahoo, TIKR) bloccano lo scraping."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace").strip()


def resolve_source(value: str | None, label: str, required: bool = False) -> str:
    """
    Risolve un input in testo:
      - None / vuoto / "non disponibile" → non disponibile
      - URL → download
      - percorso file → lettura
    """
    if value is None:
        if required:
            raise ValueError(f"{label}: obbligatorio (file SingleFile, HTML o URL)")
        return NOT_AVAILABLE

    raw = value.strip()
    if not raw or raw.lower() == NOT_AVAILABLE:
        if required:
            raise ValueError(f"{label}: obbligatorio (file SingleFile, HTML o URL)")
        return NOT_AVAILABLE

    if is_url(raw):
        print(f"[{label}] Download da URL: {raw}")
        try:
            text = fetch_url(raw)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            msg = (
                f"[{label}] Download fallito: {exc}\n"
                "  → Usa SingleFile nel browser e passa il file .html invece del link.\n"
                "  → Oppure in Cursor: @allega il file HTML + il prompt."
            )
            if required:
                raise RuntimeError(msg) from exc
            print(msg, file=sys.stderr)
            return NOT_AVAILABLE
        if not text:
            if required:
                raise RuntimeError(f"[{label}] Pagina scaricata vuota.")
            return NOT_AVAILABLE
        print(f"[{label}] OK — {len(text):,} caratteri")
        return text

    path = Path(raw).expanduser()
    if not path.is_file():
        # prova anche relativo a input/
        alt = INPUT_DIR / raw
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(
                f"[{label}] File non trovato: {raw}\n"
                f"  Metti il file SingleFile in: {INPUT_DIR}"
            )

    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        if required:
            raise ValueError(f"[{label}] File vuoto: {path}")
        return NOT_AVAILABLE
    print(f"[{label}] File letto: {path.name} ({len(text):,} caratteri)")
    return text


def normalize_sector(value: str) -> str:
    return _normalize_sector(value)


def build_prompt(
    investing_data: str,
    yahoo_data: str,
    tikr_data: str,
    sector: str,
) -> str:
    template = PROMPT_FILE.read_text(encoding="utf-8")
    return (
        template.replace("{{INVESTING_DATA}}", investing_data.strip())
        .replace("{{YAHOO_DATA}}", yahoo_data.strip())
        .replace("{{TIKR_DATA}}", tikr_data.strip())
        .replace("{{SECTOR}}", normalize_sector(sector))
    )


def default_output_name(sector: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"analisi_{sector.lower()}_{stamp}.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Genera il prompt di analisi azionaria. "
            "Preferisci file SingleFile (.html) — non serve incollare l'HTML."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi (CONSIGLIATO — file SingleFile):
  python analizza_azione.py --sector BDC --investing input/oxsq.html --open
  python analizza_azione.py --sector REIT -i input/o.html -y input/o_yahoo.html -t input/o_tikr.html

Esempi con URL (può fallire se il sito blocca lo scraping):
  python analizza_azione.py --sector GENERICO -i "https://www.investing.com/equities/apple-computer-inc"

Modalità interattiva (file / URL / skip):
  python analizza_azione.py --interactive

In Cursor senza script:
  1) SingleFile → salva HTML in input/
  2) Nella chat: @PROMPT_UNIFICATO.txt @input/oxsq.html  + scrivi "SECTOR: BDC"
        """,
    )
    parser.add_argument(
        "--investing", "-i",
        help="File SingleFile/HTML oppure URL Investing.com",
    )
    parser.add_argument(
        "--yahoo", "-y",
        help=f"File HTML/TXT oppure URL Yahoo (default: {NOT_AVAILABLE})",
    )
    parser.add_argument(
        "--tikr", "-t",
        help=f"File HTML/TXT oppure URL TIKR (default: {NOT_AVAILABLE})",
    )
    parser.add_argument(
        "--sector", "-s",
        choices=sorted({s.lower() for s in SECTORS} | {"banca", "utilities", "financial", "health"}),
        help="Settore: REIT, BDC, FINANCIALS, TECH, ENERGY, HEALTHCARE, CONSUMER, INDUSTRIAL, COMMUNICATION, GENERICO",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="File di output (default: output/analisi_<sector>_<timestamp>.txt)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Chiede file/URL per ogni fonte (niente copia-incolla HTML)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Apri il file generato con l'app predefinita di Windows",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Stampa il prompt su stdout invece di salvarlo su file",
    )
    return parser.parse_args()


def ask_source(label: str, required: bool = False) -> str:
    print(f"\n--- {label} ---")
    print("  Opzioni:")
    print("  1) Percorso file SingleFile (.html)  ← CONSIGLIATO")
    print("  2) URL della pagina")
    if not required:
        print(f"  3) Invio vuoto = {NOT_AVAILABLE}")
    while True:
        value = input(f"{label} (file / URL): ").strip().strip('"')
        if not value:
            if required:
                print("Obbligatorio. Inserisci un file o un URL.")
                continue
            return NOT_AVAILABLE
        try:
            return resolve_source(value, label, required=required)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(f"Errore: {exc}")
            if required:
                continue
            return NOT_AVAILABLE


def interactive_input() -> tuple[str, str, str, str]:
    print("\n=== ANALISI AZIONE — File / URL (niente copia HTML) ===")
    print(f"Cartella input suggerita: {INPUT_DIR}")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    investing = ask_source("INVESTING.COM", required=True)
    yahoo = ask_source("YAHOO FINANCE", required=False)
    tikr = ask_source("TIKR", required=False)

    print(f"\nSettori disponibili: {', '.join(SECTORS)}")
    while True:
        sector = input("Settore: ").strip().upper()
        if sector in SECTORS:
            break
        print(f"Settore non valido. Scegli tra: {', '.join(SECTORS)}")

    return investing, yahoo, tikr, sector


def open_file(path: Path) -> None:
    if sys.platform == "win32":
        import os
        os.startfile(path)  # noqa: S606
    else:
        print(f"Apri manualmente: {path}")


def main() -> int:
    args = parse_args()

    if not PROMPT_FILE.is_file():
        print(f"Errore: manca {PROMPT_FILE}", file=sys.stderr)
        return 1

    try:
        if args.interactive:
            investing, yahoo, tikr, sector = interactive_input()
        else:
            if not args.investing:
                print(
                    "Errore: specifica --investing FILE_O_URL oppure --interactive",
                    file=sys.stderr,
                )
                return 1
            if not args.sector:
                print(
                    "Errore: specifica --sector (vedi --help)",
                    file=sys.stderr,
                )
                return 1
            investing = resolve_source(args.investing, "INVESTING.COM", required=True)
            yahoo = resolve_source(args.yahoo, "YAHOO FINANCE", required=False)
            tikr = resolve_source(args.tikr, "TIKR", required=False)
            sector = normalize_sector(args.sector)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    prompt = build_prompt(investing, yahoo, tikr, sector)

    if args.stdout:
        sys.stdout.write(prompt)
        return 0

    out_path = args.output
    if out_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / default_output_name(sector)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(prompt, encoding="utf-8")

    print(f"\nPrompt generato: {out_path}")
    print(f"Settore: {sector}")
    print("Prossimo passo: apri il file e incollalo in Cursor/ChatGPT.")
    print(
        "Oppure in Cursor: @PROMPT_UNIFICATO.txt @file.html + SECTOR senza generare nulla."
    )

    if args.open:
        open_file(out_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
