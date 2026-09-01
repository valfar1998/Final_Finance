"""Verifica catalizzatore news via LLM leggero (Groq / Gemini). Fallback keyword se assente."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from finance_alert.config import LlmRules
from finance_alert.models import NewsItem

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

PROMPT = """Sei un filtro per alert trading swing (2-7 giorni).
Analizza headline e publisher. Rispondi SOLO con JSON valido, nessun altro testo:
{"is_catalyst": true|false, "impact_score": 1-10, "driver": "breve motivo"}

is_catalyst=true SOLO con driver operativo verificabile:
- guidance raised/cut, beat/miss utili, M&A, FDA, contratto materiale, downgrade/upgrade analyst
Rifiuta: opinioni, promo, top pick, recap generici, rumor vaghi.

Ticker: {ticker}
Publisher: {publisher}
Headline: {headline}
"""

EQUIV_PROMPT = """Confronta due headline sullo stesso titolo. Rispondi SOLO JSON:
{"equivalent": true|false}

equivalent=true se descrivono lo stesso evento/fatto (anche con titoli diversi).
equivalent=false se sono notizie diverse o generiche.

Ticker: {ticker}
Headline A: {headline_a}
Headline B: {headline_b}
"""


@dataclass
class LlmVerdict:
    approved: bool
    score: int = 0
    driver: str = ""
    provider: str = "keyword"
    verified: bool = True
    unverified: bool = False


PRIMARY_CATALYSTS = (
    "guidance raised",
    "raises guidance",
    "raised guidance",
    "beat estimates",
    "beats estimates",
    "earnings beat",
    "fda approval",
    "fda approves",
    "fda approved",
    "merger",
    "acquisition",
    "to acquire",
    "buyout",
    "takeover",
)


def _has_primary_catalyst(headline: str) -> bool:
    text = (headline or "").lower()
    return any(key in text for key in PRIMARY_CATALYSTS)


def _provider() -> str:
    forced = (os.getenv("NEWS_LLM_PROVIDER") or "").strip().lower()
    if forced in {"off", "none", "false", "0"}:
        return "off"
    if forced in {"groq", "gemini"}:
        return forced
    if os.getenv("GROQ_API_KEY", "").strip():
        return "groq"
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "off"


def llm_available() -> bool:
    return _provider() != "off"


def _parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _post_json(url: str, payload: dict, headers: dict[str, str], *, timeout: float) -> dict | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _from_parsed(parsed: dict, provider: str) -> LlmVerdict:
    approved = bool(parsed.get("is_catalyst", parsed.get("approve")))
    score = int(parsed.get("impact_score") or parsed.get("score") or 0)
    driver = str(parsed.get("driver") or "").strip()[:180]
    if score <= 0:
        score = 7 if approved else 3
    return LlmVerdict(approved=approved, score=score, driver=driver, provider=provider, verified=True)


def _call_groq(item: NewsItem, timeout: float) -> LlmVerdict | None:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    body = {
        "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "temperature": 0,
        "max_tokens": 120,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": PROMPT.format(
                    ticker=item.ticker,
                    publisher=item.publisher or item.source or "n.d.",
                    headline=item.headline,
                ),
            }
        ],
    }
    raw = _post_json(
        GROQ_URL,
        body,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    if not raw:
        return None
    try:
        text = raw["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError):
        return None
    parsed = _parse_json(str(text))
    if not parsed:
        return None
    return _from_parsed(parsed, "groq")


def _call_gemini(item: NewsItem, timeout: float) -> LlmVerdict | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    url = f"{GEMINI_URL}?key={key}"
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": PROMPT.format(
                            ticker=item.ticker,
                            publisher=item.publisher or item.source or "n.d.",
                            headline=item.headline,
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 120,
            "responseMimeType": "application/json",
        },
    }
    raw = _post_json(url, body, {"Content-Type": "application/json"}, timeout=timeout)
    if not raw:
        return None
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
    except (TypeError, KeyError, IndexError):
        return None
    parsed = _parse_json(str(text))
    if not parsed:
        return None
    return _from_parsed(parsed, "gemini")


def verify_news_catalyst(item: NewsItem, *, rules: LlmRules | None = None, min_score: int = 6) -> LlmVerdict:
    llm = rules or LlmRules()
    min_score = llm.min_llm_score if rules else min_score
    timeout = llm.timeout_sec

    provider = _provider()
    if provider == "off":
        return LlmVerdict(approved=True, score=item.score, driver="keyword-only", provider="keyword")

    verdict = _call_groq(item, timeout) if provider == "groq" else _call_gemini(item, timeout)
    if verdict is None:
        if _has_primary_catalyst(item.headline):
            return LlmVerdict(
                approved=True,
                score=6,
                driver="primary-catalyst-fallback",
                provider="fallback",
                verified=False,
                unverified=True,
            )
        return LlmVerdict(
            approved=False,
            score=min(item.score, 5),
            driver="llm-timeout",
            provider="fallback",
            verified=False,
        )
    if verdict.approved and verdict.score < min_score:
        verdict.approved = False
    return verdict


def _call_equiv_groq(headline_a: str, headline_b: str, ticker: str, timeout: float) -> bool | None:
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    body = {
        "model": os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        "temperature": 0,
        "max_tokens": 40,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": EQUIV_PROMPT.format(
                    ticker=ticker,
                    headline_a=headline_a[:240],
                    headline_b=headline_b[:240],
                ),
            }
        ],
    }
    raw = _post_json(
        GROQ_URL,
        body,
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        timeout=timeout,
    )
    if not raw:
        return None
    try:
        text = raw["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError):
        return None
    parsed = _parse_json(str(text))
    if not parsed:
        return None
    return bool(parsed.get("equivalent"))


def _call_equiv_gemini(headline_a: str, headline_b: str, ticker: str, timeout: float) -> bool | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    url = f"{GEMINI_URL}?key={key}"
    body = {
        "contents": [
            {
                "parts": [
                    {
                        "text": EQUIV_PROMPT.format(
                            ticker=ticker,
                            headline_a=headline_a[:240],
                            headline_b=headline_b[:240],
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 40,
            "responseMimeType": "application/json",
        },
    }
    raw = _post_json(url, body, {"Content-Type": "application/json"}, timeout=timeout)
    if not raw:
        return None
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
    except (TypeError, KeyError, IndexError):
        return None
    parsed = _parse_json(str(text))
    if not parsed:
        return None
    return bool(parsed.get("equivalent"))


def headlines_equivalent(headline_a: str, headline_b: str, *, ticker: str, timeout: float = 2.0) -> bool:
    if not headline_a.strip() or not headline_b.strip():
        return False
    provider = _provider()
    if provider == "off":
        return False
    result = (
        _call_equiv_groq(headline_a, headline_b, ticker, timeout)
        if provider == "groq"
        else _call_equiv_gemini(headline_a, headline_b, ticker, timeout)
    )
    return bool(result)
