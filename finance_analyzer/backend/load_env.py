"""Load environment variables from .env (write API keys once)."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_LOADED_FROM: Path | None = None


def bootstrap_env() -> Path | None:
    """Load .env from project root or backend folder (first found)."""
    global _LOADED_FROM
    if _LOADED_FROM is not None:
        return _LOADED_FROM

    backend = Path(__file__).resolve().parent
    for candidate in (backend.parent / ".env", backend / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            _LOADED_FROM = candidate
            return candidate
    return None


def env_file_display() -> str | None:
    if _LOADED_FROM is None:
        bootstrap_env()
    return str(_LOADED_FROM) if _LOADED_FROM else None
