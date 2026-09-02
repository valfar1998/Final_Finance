"""Korea FSS OpenDART — filings/disclosure API (free API key).

Docs: https://opendart.fss.or.kr/
Register: https://opendart.fss.or.kr/guide/main.do?menuCd=O01
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from finance_alert.env import env_key
from finance_alert.regulatory.base import get_json

BASE = "https://opendart.fss.or.kr/api"

# Stock code (6 cifre KRX) → corp_code OpenDART (8 cifre)
# Aggiorna quando aggiungi ticker KR in watchlist.
_CORP_CODES: dict[str, str] = {
    "005930": "00126380",  # Samsung Electronics
    "000660": "00164779",  # SK hynix
    "035420": "00266961",  # NAVER
    "035720": "00258801",  # Kakao
    "051910": "00356361",  # LG Chem
    "006400": "00126362",  # Samsung SDI
    "068270": "00413013",  # Celltrion
    "005380": "00164742",  # Hyundai Motor
    "000270": "00164788",  # Kia
}


@dataclass
class DartDisclosure:
    corp_name: str
    report_nm: str
    rcept_no: str
    rcept_dt: str
    flr_nm: str = ""


@dataclass
class OpenDartResult:
    ticker: str
    stock_code: str = ""
    corp_code: str = ""
    disclosures: list[DartDisclosure] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def _normalize_kr_ticker(ticker: str) -> str:
    t = ticker.upper().strip()
    for suf in (".KS", ".KQ"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            break
    digits = "".join(ch for ch in t if ch.isdigit())
    return digits.zfill(6) if digits else t


def filings_for_ticker(ticker: str, *, lookback_days: int = 14) -> OpenDartResult:
    """Recent OpenDART disclosures for a KRX/KOSDAQ ticker."""
    out = OpenDartResult(ticker=ticker)
    key = env_key("OPEN_DART_API_KEY")
    if not key:
        out.error = "OPEN_DART_API_KEY mancante"
        return out

    stock = _normalize_kr_ticker(ticker)
    out.stock_code = stock
    corp = _CORP_CODES.get(stock)
    if not corp:
        out.error = f"corp_code OpenDART non mappato per {stock}"
        out.notes.append("Aggiungi mapping in opendart._CORP_CODES")
        return out
    out.corp_code = corp

    end = date.today()
    start = end - timedelta(days=max(1, lookback_days))
    try:
        data = get_json(
            f"{BASE}/list.json",
            params={
                "crtfc_key": key,
                "corp_code": corp,
                "bgn_de": start.strftime("%Y%m%d"),
                "end_de": end.strftime("%Y%m%d"),
                "page_count": "20",
            },
        )
    except RuntimeError as exc:
        out.error = str(exc)[:120]
        return out

    status = str((data or {}).get("status") or "")
    message = str((data or {}).get("message") or "")
    if status and status not in {"000", "013"}:
        # 013 = no data
        out.error = f"OpenDART {status}: {message[:80]}"
        return out
    if status == "013":
        out.notes.append(f"Nessun disclosure recente per {stock}")
        return out

    for row in _rows(data):
        out.disclosures.append(
            DartDisclosure(
                corp_name=str(row.get("corp_name") or ""),
                report_nm=str(row.get("report_nm") or ""),
                rcept_no=str(row.get("rcept_no") or ""),
                rcept_dt=str(row.get("rcept_dt") or ""),
                flr_nm=str(row.get("flr_nm") or ""),
            )
        )
    if not out.disclosures:
        out.notes.append(f"Nessun disclosure OpenDART recente per {stock}")
    return out


def _rows(data: Any) -> list[dict]:
    if not isinstance(data, dict):
        return []
    block = data.get("list") or []
    if isinstance(block, list):
        return [x for x in block if isinstance(x, dict)]
    return []
