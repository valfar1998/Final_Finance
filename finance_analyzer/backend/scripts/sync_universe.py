"""Sync global stock universe into local database."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from load_env import bootstrap_env  # noqa: E402

bootstrap_env()

from services.universe import sync_universe  # noqa: E402


def main() -> int:
    force = "--force" in sys.argv
    result = sync_universe(force=force)
    print("Status:", result["status"])
    print("Totale simboli:", result.get("total"))
    if result.get("by_region"):
        print("Per regione:")
        for region, count in result["by_region"].items():
            print(f"  {region}: {count}")
    if result.get("note"):
        print("Nota:", result["note"])
    return 0 if result.get("status") in ("ok", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
