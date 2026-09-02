"""Sync ETF universe (USA NASDAQ + international Finnhub)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from load_env import bootstrap_env  # noqa: E402

bootstrap_env()

from services.universe import sync_etfs  # noqa: E402


def main() -> int:
    force = "--force" in sys.argv
    result = sync_etfs(force=force)
    print("Status:", result["status"])
    print("ETF totali:", result.get("total_etf"))
    if result.get("by_type"):
        print("Per tipo:")
        for t, count in result["by_type"].items():
            print(f"  {t}: {count}")
    if result.get("us_etf_added") is not None:
        print("ETF USA aggiunti/aggiornati:", result.get("us_etf_added"))
    if result.get("intl_etf_added") is not None:
        print("ETF intl aggiunti/aggiornati:", result.get("intl_etf_added"))
    if result.get("note"):
        print("Nota:", result["note"])
    return 0 if result.get("status") in ("ok", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
