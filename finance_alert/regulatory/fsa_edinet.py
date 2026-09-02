"""Japan FSA — EDINET API (filings by date, free subscription key)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from finance_alert.env import env_key
from finance_alert.regulatory.base import get_json

BASE = "https://api.edinet-fsa.go.jp/api/v2"


@dataclass
class EdinetFiling:
    edinet_code: str
    sec_code: str
    company: str
    doc_type: str
    doc_id: str
    submit_date: str
    pdf_url: str = ""


@dataclass
class EdinetResult:
    ticker: str
    filings: list[EdinetFiling] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def _headers() -> dict[str, str]:
    key = env_key("FSA_EDINET_API_KEY")
    if not key:
        return {}
    return {"Ocp-Apim-Subscription-Key": key}


def _normalize_jp_ticker(ticker: str) -> str:
    t = ticker.upper().strip()
    if t.endswith(".T"):
        t = t[:-2]
    return t.zfill(4) if t.isdigit() else t


def filings_for_ticker(ticker: str, *, lookback_days: int = 14) -> EdinetResult:
    """Scan recent EDINET submissions and filter by securities code."""
    out = EdinetResult(ticker=ticker)
    hdrs = _headers()
    if not hdrs:
        out.error = "FSA_EDINET_API_KEY mancante"
        return out
    sec = _normalize_jp_ticker(ticker)
    today = date.today()
    for offset in range(lookback_days):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        ds = day.isoformat()
        try:
            data = get_json(
                f"{BASE}/documents.json",
                headers=hdrs,
                params={"date": ds, "type": "2"},
            )
        except RuntimeError as exc:
            out.notes.append(str(exc)[:80])
            continue
        for row in _rows(data):
            code = str(row.get("secCode") or row.get("secCodeStr") or "").strip()
            if not code:
                continue
            code_norm = code.zfill(4) if code.isdigit() else code
            if code_norm != sec and not sec.endswith(code_norm):
                continue
            out.filings.append(
                EdinetFiling(
                    edinet_code=str(row.get("edinetCode") or ""),
                    sec_code=code_norm,
                    company=str(row.get("filerName") or row.get("docDescription") or ""),
                    doc_type=str(row.get("docTypeCode") or row.get("formCode") or ""),
                    doc_id=str(row.get("docID") or ""),
                    submit_date=ds,
                    pdf_url=str(row.get("pdfUrl") or row.get("docPdfUrl") or ""),
                )
            )
    if not out.filings:
        out.notes.append(f"Nessun filing EDINET recente per {sec}")
    return out


def _rows(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    block = data.get("results") or data.get("Results") or []
    if isinstance(block, list):
        return [x for x in block if isinstance(x, dict)]
    return []
