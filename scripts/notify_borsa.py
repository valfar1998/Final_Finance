#!/usr/bin/env python3
"""Entry-point per GitHub Actions / cron. Stesso schema di notify_scadenze."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finance_alert.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
