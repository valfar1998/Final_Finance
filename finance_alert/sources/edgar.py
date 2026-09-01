"""SEC EDGAR: ufficiale, gratis, nessuna API key. Serve User-Agent con email."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from finance_alert.config import Ticker
from finance_alert.env import ROOT, env_key
from finance_alert.http import HttpError, get_json, map_parallel
from finance_alert.models import Filing

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
ATOM_8K_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=8-K&company=&dateb=&owner=include&count=40&output=atom"
)
CACHE = ROOT / "data" / "cik_cache.json"
_CIK_TITLE_RE = re.compile(r"\((\d{10})\)")
_ACCESSION_RE = re.compile(r"accession-number=([\d-]+)", re.IGNORECASE)


def _ua() -> str:
    email = env_key("SEC_CONTACT_EMAIL") or "finance-alert@localhost"
    return f"finance-alert/1.0 (personal project; {email})"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": _ua(),
        "Accept": "application/json",
    }


def _atom_headers() -> dict[str, str]:
    return {
        "User-Agent": _ua(),
        "Accept": "application/atom+xml, application/xml, text/xml, */*",
    }


def _get_atom_xml() -> str | None:
    req = urllib.request.Request(ATOM_8K_URL, headers=_atom_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _atom_accession(entry: ET.Element, link: str) -> str:
    entry_id = entry.findtext("{*}id") or entry.findtext("id") or ""
    match = _ACCESSION_RE.search(entry_id)
    if match:
        return match.group(1)
    match = _ACCESSION_RE.search(link)
    if match:
        return match.group(1)
    parts = [p for p in link.split("/") if p]
    for part in reversed(parts):
        if re.fullmatch(r"\d{10}-\d{2}-\d{6}", part):
            return part
    return ""


def _parse_atom_filings(
    xml: str,
    *,
    cik_to_ticker: dict[str, str],
    wanted_forms: set[str],
) -> list[Filing]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out: list[Filing] = []
    entries = root.findall(".//{*}entry") or root.findall("./entry")
    for entry in entries[:40]:
        title = (entry.findtext("{*}title") or entry.findtext("title") or "").strip()
        if not title:
            continue
        form = title.split(" - ", 1)[0].strip().upper()
        if form not in wanted_forms:
            continue
        cik_match = _CIK_TITLE_RE.search(title)
        if not cik_match:
            continue
        cik = cik_match.group(1)
        ticker = cik_to_ticker.get(cik)
        if not ticker:
            continue
        link = ""
        for node in entry.findall("{*}link") + entry.findall("link"):
            href = (node.attrib.get("href") or "").strip()
            if href:
                link = href
                break
        if not link:
            continue
        accession = _atom_accession(entry, link)
        if not accession:
            continue
        updated = (entry.findtext("{*}updated") or entry.findtext("updated") or "")[:10]
        out.append(
            Filing(
                ticker=ticker,
                form=form,
                accession=accession,
                filed=updated,
                items="",
                url=link,
            )
        )
    return out


def _atom_filings_for_watchlist(
    tickers: list[Ticker],
    forms: list[str],
) -> list[Filing]:
    xml = _get_atom_xml()
    if not xml:
        return []
    cik_map = resolve_cik(tickers)
    cik_to_ticker = {cik: ticker for ticker, cik in cik_map.items()}
    wanted = {f.upper() for f in forms}
    return _parse_atom_filings(xml, cik_to_ticker=cik_to_ticker, wanted_forms=wanted)


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


def _filings_for_ticker(
    item: Ticker,
    cik: str,
    wanted: set[str],
    limit: int,
) -> list[Filing]:
    try:
        data = get_json(SUBMISSIONS.format(cik=cik), headers=_headers(), timeout=25)
    except (HttpError, OSError, TimeoutError, ValueError):
        return []
    recent = ((data or {}).get("filings") or {}).get("recent") or {}
    forms_col = recent.get("form") or []
    acc_col = recent.get("accessionNumber") or []
    date_col = recent.get("filingDate") or []
    items_col = recent.get("items") or [""] * len(forms_col)
    primary = recent.get("primaryDocument") or [""] * len(forms_col)
    out: list[Filing] = []
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
        if len(out) >= limit:
            break
    return out


def fetch_filings(tickers: list[Ticker], forms: list[str], limit: int = 8) -> list[Filing]:
    cik_map = resolve_cik(tickers)
    wanted = {f.upper() for f in forms}
    jobs = [(item, cik_map[item.ticker]) for item in tickers if item.ticker in cik_map]
    out: list[Filing] = []
    if jobs:

        def _one(pair: tuple[Ticker, str]) -> list[Filing]:
            item, cik = pair
            return _filings_for_ticker(item, cik, wanted, limit)

        batches = map_parallel(_one, jobs, max_workers=min(4, len(jobs)))
        for batch in batches:
            out.extend(batch)

    # Backup: feed Atom SEC (1 richiesta) per filing non presenti nell'API submissions
    known = {f.accession for f in out if f.accession}
    atom_rows = _atom_filings_for_watchlist(tickers, forms)
    refresh: set[str] = set()
    for row in atom_rows:
        if row.accession in known:
            continue
        refresh.add(row.ticker)
    if refresh:
        extra_jobs = [(item, cik_map[item.ticker]) for item in tickers if item.ticker in refresh]
        for item, cik in extra_jobs:
            for filing in _filings_for_ticker(item, cik, wanted, limit):
                if filing.accession not in known:
                    out.append(filing)
                    known.add(filing.accession)
    return out
