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
Analizza headline e publisher. Rispondi SOLO JSON valido:
{"is_catalyst": true|false, "impact_score": 1-10, "driver": "breve motivo"}

is_catalyst=true SOLO con driver operativo verificabile:
- guidance raised/cut, beat/miss utili, M&A, FDA, contratto materiale, downgrade/upgrade analyst
Rifiuta: opinioni, promo, top pick, recap generici, rumor vaghi.

Ticker: {ticker}
Publisher: {publisher}
Headline: {headline}
"""


@dataclass
class LlmVerdict:
    approved: bool
    score: int = 0
    driver: str = ""
    provider: str = "keyword"
    verified: bool = True
    unverified: bool = False


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
        "generationConfig": {"temperature": 0, "maxOutputTokens": 120},
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
    fallback_score = llm.fallback_keyword_score

    provider = _provider()
    if provider == "off":
        return LlmVerdict(approved=True, score=item.score, driver="keyword-only", provider="keyword")

    verdict = _call_groq(item, timeout) if provider == "groq" else _call_gemini(item, timeout)
    if verdict is None:
        if item.score >= fallback_score:
            return LlmVerdict(
                approved=True,
                score=item.score,
                driver="keyword-fallback",
                provider="fallback",
                verified=False,
                unverified=True,
            )
        return LlmVerdict(
            approved=False,
            score=item.score,
            driver="llm-timeout",
            provider="fallback",
            verified=False,
        )
    if verdict.approved and verdict.score < min_score:
        verdict.approved = False
    return verdict
