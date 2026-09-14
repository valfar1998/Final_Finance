#!/usr/bin/env python3
"""Scarica PDF Trade Republic e aggiorna data/tr_us_universe.json (ISIN/nome/ticker)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_alert.env import load_env
from finance_alert.tr_universe import sync_from_pdf


def main() -> int:
    load_env()
    parser = argparse.ArgumentParser(description="Sync universo Trade Republic US")
    parser.add_argument(
        "--map",
        type=int,
        default=200,
        help="Quanti ISIN mappare via OpenFIGI (0=nessuno, -1=tutti). Default 200",
    )
    parser.add_argument("--no-download", action="store_true", help="Usa PDF già in data/")
    parser.add_argument("--openfigi-key", default="", help="API key OpenFIGI opzionale")
    args = parser.parse_args()
    result = sync_from_pdf(
        map_limit=args.map,
        api_key=args.openfigi_key or "",
        download=not args.no_download,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
