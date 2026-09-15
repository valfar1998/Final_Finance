"""Universo azioni USA su Trade Republic (PDF ufficiale → ISIN/nome/ticker)."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from finance_alert.env import ROOT
from finance_alert.http import DEFAULT_UA
from finance_alert.models import is_quoteable_ticker

TR_PDF_URL = "https://assets.traderepublic.com/assets/files/DE/Instrument_Universe_DE_en.pdf"
DEFAULT_PATH = ROOT / "data" / "tr_us_universe.json"
PDF_PATH = ROOT / "data" / "tr_universe_de.pdf"
OPENFIGI = "https://api.openfigi.com/v3/mapping"

_EXCLUDE_NAME = re.compile(
    r"\b(Fund|ETF|ETN|Notes|Bond|Preferred|Pref\.|Warrant|Unit)\b",
    re.I,
)
_ISIN_LINE = re.compile(r"^(US[0-9A-Z]{10})\s+(.+)$")
_SUFFIX = re.compile(
    r"\s*\((?:ADR|GDR|ADS|ORD|Ord\.?|Registered Shares[^)]*)\)\s*$",
    re.I,
)


@dataclass(frozen=True)
class TrInstrument:
    isin: str
    name: str
    ticker: str = ""

    def equity_like(self) -> bool:
        return not bool(_EXCLUDE_NAME.search(self.name or ""))


def _norm_name(name: str) -> str:
    text = _SUFFIX.sub("", (name or "").strip())
    text = re.sub(r"[^A-Za-z0-9 &\-./]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def download_pdf(path: Path = PDF_PATH, url: str = TR_PDF_URL) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        path.write_bytes(resp.read())
    return path


def extract_us_from_pdf(pdf_path: Path = PDF_PATH) -> list[TrInstrument]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Serve pypdf: pip install pypdf") from exc
    reader = PdfReader(str(pdf_path))
    seen: set[str] = set()
    out: list[TrInstrument] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            m = _ISIN_LINE.match(line.strip())
            if not m:
                continue
            isin, name = m.group(1), m.group(2).strip()
            if isin in seen:
                continue
            seen.add(isin)
            out.append(TrInstrument(isin=isin, name=name))
    return out


def _openfigi_map(isins: list[str], *, api_key: str = "") -> dict[str, str]:
    """ISIN → ticker Yahoo-like (solo Equity US quando possibile)."""
    if not isins:
        return {}
    jobs = [{"idType": "ID_ISIN", "idValue": i} for i in isins]
    body = json.dumps(jobs).encode()
    headers = {"Content-Type": "application/json", "User-Agent": DEFAULT_UA}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key
    req = urllib.request.Request(OPENFIGI, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        rows = json.loads(resp.read().decode())
    mapped: dict[str, str] = {}
    for isin, row in zip(isins, rows):
        if not isinstance(row, dict):
            continue
        data = row.get("data")
        if not isinstance(data, list) or not data:
            continue
        pick = None
        for cand in data:
            if not isinstance(cand, dict):
                continue
            exch = str(cand.get("exchCode") or "")
            ticker = str(cand.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            if exch in {"US", "UA", "UN", "UQ", "UW", "N", "NYSE", "NASDAQ"}:
                pick = ticker
                break
            if pick is None:
                pick = ticker
        if pick:
            # Class share: BRK/B → BRK.B; scarta preferred/perp con spazi
            cleaned = pick.replace("/", ".")
            if is_quoteable_ticker(cleaned):
                mapped[isin] = cleaned
    return mapped


def map_tickers(
    instruments: list[TrInstrument],
    *,
    existing: dict[str, str] | None = None,
    batch_size: int = 8,
    pause_sec: float = 1.1,
    api_key: str = "",
    limit: int = 0,
) -> list[TrInstrument]:
    known = dict(existing or {})
    need = [i for i in instruments if i.isin not in known or not known.get(i.isin)]
    if limit > 0:
        need = need[:limit]
    for idx in range(0, len(need), batch_size):
        chunk = need[idx : idx + batch_size]
        try:
            got = _openfigi_map([c.isin for c in chunk], api_key=api_key)
            known.update(got)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(max(pause_sec * 3, 5.0))
                continue
            # 413 / altri: riduci batch e riprova una volta
            if exc.code == 413 and len(chunk) > 1:
                mid = max(1, len(chunk) // 2)
                for sub in (chunk[:mid], chunk[mid:]):
                    try:
                        known.update(_openfigi_map([c.isin for c in sub], api_key=api_key))
                    except Exception:
                        pass
                    time.sleep(pause_sec)
            continue
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(pause_sec)
    return [
        TrInstrument(isin=i.isin, name=i.name, ticker=known.get(i.isin, i.ticker))
        for i in instruments
    ]


def save_universe(instruments: list[TrInstrument], path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    equities = [i for i in instruments if i.equity_like()]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": TR_PDF_URL,
        "n_total": len(instruments),
        "n_equity": len(equities),
        "n_mapped": sum(1 for i in equities if i.ticker),
        "instruments": [
            {"isin": i.isin, "name": i.name, "ticker": i.ticker}
            for i in instruments
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_universe(path: Path | None = None) -> list[TrInstrument]:
    target = path or DEFAULT_PATH
    if not target.is_file():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("instruments") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[TrInstrument] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        isin = str(row.get("isin") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker and not is_quoteable_ticker(ticker):
            ticker = ""
        if not isin or not name:
            continue
        out.append(TrInstrument(isin=isin, name=name, ticker=ticker))
    return out


def load_equity_universe(path: Path | None = None) -> list[TrInstrument]:
    return [i for i in load_universe(path) if i.equity_like()]


class NameMatcher:
    """Match headline → strumento TR (nomi lunghi prima; evita match corti)."""

    def __init__(self, instruments: list[TrInstrument], *, min_name_len: int = 5) -> None:
        self.min_name_len = min_name_len
        self._by_ticker: dict[str, TrInstrument] = {}
        self._name_patterns: list[tuple[re.Pattern[str], TrInstrument]] = []
        for inst in instruments:
            tick = (inst.ticker or "").strip().upper()
            # Solo ticker quoteable: evita match su "MSTR 12 PERP A" / bond OpenFIGI
            if tick and is_quoteable_ticker(tick):
                self._by_ticker[tick] = inst
            clean = _norm_name(inst.name)
            if len(clean) < min_name_len:
                continue
            # Evita match su token generici
            if clean.upper() in {"INC", "CORP", "GROUP", "HOLDINGS", "COMPANY", "TECH"}:
                continue
            pat = re.compile(rf"(?<![A-Za-z0-9]){re.escape(clean)}(?![A-Za-z0-9])", re.I)
            self._name_patterns.append((pat, inst))
        self._name_patterns.sort(key=lambda x: len(x[1].name), reverse=True)

    def match(self, headline: str) -> TrInstrument | None:
        text = (headline or "").strip()
        if not text:
            return None
        upper = text.upper()
        # Ticker espliciti (4+ lettere o noti)
        for ticker, inst in self._by_ticker.items():
            if len(ticker) < 2:
                continue
            if re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", upper):
                return inst
        for pat, inst in self._name_patterns:
            if pat.search(text):
                # Nome matchato ma ticker OpenFIGI inutilizzabile → ignora
                if inst.ticker and not is_quoteable_ticker(inst.ticker):
                    continue
                return inst
        return None


_matcher_cache: tuple[float, NameMatcher] | None = None


def get_matcher(*, min_name_len: int = 5, reload: bool = False) -> NameMatcher | None:
    global _matcher_cache
    instruments = load_equity_universe()
    if not instruments:
        return None
    mtime = DEFAULT_PATH.stat().st_mtime if DEFAULT_PATH.is_file() else 0.0
    if not reload and _matcher_cache and _matcher_cache[0] == mtime:
        return _matcher_cache[1]
    matcher = NameMatcher(instruments, min_name_len=min_name_len)
    _matcher_cache = (mtime, matcher)
    return matcher


def resolve_ticker(isin: str, *, api_key: str = "") -> str | None:
    """Risolve un ISIN e aggiorna la cache su disco."""
    isin = isin.strip().upper()
    if not isin:
        return None
    instruments = load_universe()
    existing = {i.isin: i.ticker for i in instruments if i.ticker}
    if existing.get(isin):
        return existing[isin]
    try:
        got = _openfigi_map([isin], api_key=api_key)
    except Exception:
        return None
    tick = got.get(isin)
    if not tick or not is_quoteable_ticker(tick):
        return None
    updated = [
        TrInstrument(isin=i.isin, name=i.name, ticker=tick if i.isin == isin else i.ticker)
        for i in instruments
    ]
    if updated:
        save_universe(updated)
    return tick


def sync_from_pdf(
    *,
    map_limit: int = 0,
    api_key: str = "",
    download: bool = True,
) -> dict[str, Any]:
    if download or not PDF_PATH.is_file():
        download_pdf()
    instruments = extract_us_from_pdf()
    existing = {i.isin: i.ticker for i in load_universe() if i.ticker}
    # preserva ticker già mappati
    merged = [
        TrInstrument(isin=i.isin, name=i.name, ticker=existing.get(i.isin, ""))
        for i in instruments
    ]
    if map_limit != 0:
        # map_limit < 0 → tutti i non mappati; >0 → cap
        cap = 0 if map_limit < 0 else map_limit
        merged = map_tickers(
            merged,
            existing=existing,
            api_key=api_key,
            limit=cap,
        )
    path = save_universe(merged)
    equities = [i for i in merged if i.equity_like()]
    return {
        "path": str(path),
        "n_total": len(merged),
        "n_equity": len(equities),
        "n_mapped": sum(1 for i in equities if i.ticker),
    }
