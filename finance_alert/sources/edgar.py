"""SEC EDGAR: ufficiale, gratis, nessuna API key. Serve User-Agent con email."""

from __future__ import annotations

import json
import time
from finance_alert.config import Ticker
from finance_alert.env import ROOT, env_key
from finance_alert.http import HttpError, get_json
from finance_alert.models import Filing

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
CACHE = ROOT / "data" / "cik_cache.json"


def _ua() -> str:
    email = env_key("SEC_CONTACT_EMAIL") or "finance-alert@localhost"
    return f"finance-alert/1.0 (personal project; {email})"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _ua(),
        "Accept": "application/json",
    }


def _load_cik_cache() -> dict[str, str]:
    if not CACHE.is_file():
        return {}
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k).upper(): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _save_cik_cache(mapping: dict[str, str]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(mapping, indent=2), encoding="utf-8")


def resolve_cik(tickers: list[Ticker]) -> dict[str, str]:
    mapping = _load_cik_cache()
    for item in tickers:
        if item.cik:
            mapping[item.ticker] = item.cik.zfill(10)
    missing = [t.ticker for t in tickers if t.ticker not in mapping]
    if missing:
        try:
            data = get_json(TICKERS_URL, headers=_headers(), timeout=30)
        except (HttpError, OSError, TimeoutError, ValueError):
            data = None
        if isinstance(data, dict):
            for row in data.values():
                if not isinstance(row, dict):
                    continue
                ticker = str(row.get("ticker") or "").upper()
                cik = str(row.get("cik_str") or "").zfill(10)
                if ticker and cik:
                    mapping[ticker] = cik
            _save_cik_cache(mapping)
    return {t.ticker: mapping[t.ticker] for t in tickers if t.ticker in mapping}


def fetch_filings(tickers: list[Ticker], forms: list[str], limit: int = 8) -> list[Filing]:
    cik_map = resolve_cik(tickers)
    wanted = {f.upper() for f in forms}
    out: list[Filing] = []
    for i, item in enumerate(tickers):
        cik = cik_map.get(item.ticker)
        if not cik:
            continue
        try:
            data = get_json(SUBMISSIONS.format(cik=cik), headers=_headers(), timeout=25)
        except (HttpError, OSError, TimeoutError, ValueError):
            continue
        recent = ((data or {}).get("filings") or {}).get("recent") or {}
        forms_col = recent.get("form") or []
        acc_col = recent.get("accessionNumber") or []
        date_col = recent.get("filingDate") or []
        items_col = recent.get("items") or [""] * len(forms_col)
        primary = recent.get("primaryDocument") or [""] * len(forms_col)
        for form, acc, filed, items, doc in zip(
            forms_col, acc_col, date_col, items_col, primary
        ):
            if str(form).upper() not in wanted:
                continue
            acc_s = str(acc)
            acc_path = acc_s.replace("-", "")
            url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                f"{acc_path}/{doc or acc_s + '-index.html'}"
            )
            out.append(
                Filing(
                    ticker=item.ticker,
                    form=str(form),
                    accession=acc_s,
                    filed=str(filed)[:10],
                    items=str(items or ""),
                    url=url,
                )
            )
            if sum(1 for f in out if f.ticker == item.ticker) >= limit:
                break
        if i + 1 < len(tickers):
            time.sleep(0.15)
    return out
