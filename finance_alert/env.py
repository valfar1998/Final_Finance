"""Carica .env locale e, se mancano, quelli dei progetti accanto."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIBLING_ENV_DIRS = (
    "Finance-Analyzer-main",
    "finance_analyzer",
    "football-predictor",
    "filtro_telegram_recensioni",
    "telegram-offerte-sconto",
)
KEY_NAMES = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "FINNHUB_API_KEY",
    "FMP_API_KEY",
    "TWELVE_DATA_API_KEY",
    "POLYGON_API_KEY",
    "NEWSAPI_API_KEY",
    "MARKETAUX_API_TOKEN",
    "BENZINGA_API_TOKEN",
    "ALPHA_VANTAGE_API_KEY",
    "SEC_CONTACT_EMAIL",
    "FCA_API_KEY",
    "FCA_AUTH_EMAIL",
    "FSA_EDINET_API_KEY",
    "SPIKE_PCT",
    "SURPRISE_EPS_PCT",
    "UNIFIED_MIN_SCORE",
    "UNIFIED_MIN_FUNDAMENTAL",
)


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _apply(data: dict[str, str], *, override: bool) -> None:
    for key, value in data.items():
        if not value:
            continue
        if override or key not in os.environ or not str(os.environ.get(key, "")).strip():
            os.environ[key] = value


def load_env() -> list[str]:
    """Ritorna le fonti da cui ha letto almeno una chiave utile."""
    sources: list[str] = []
    local = parse_env_file(ROOT / ".env")
    if local:
        _apply(local, override=False)
        sources.append(str(ROOT / ".env"))
    parent = ROOT.parent
    for name in SIBLING_ENV_DIRS:
        path = parent / name / ".env"
        data = parse_env_file(path)
        useful = {k: v for k, v in data.items() if k in KEY_NAMES and v}
        if not useful:
            continue
        _apply(useful, override=False)
        sources.append(str(path))
    return sources


def clean_secret(value: str) -> str:
    return "".join(str(value or "").split())


def env_key(name: str) -> str:
    return clean_secret(os.getenv(name, ""))
