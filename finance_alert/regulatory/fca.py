"""UK FCA Financial Services Register API (free, requires registration)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finance_alert.env import env_key
from finance_alert.regulatory.base import get_json

BASE = "https://register.fca.org.uk/services/V0.1"


@dataclass
class FcaResult:
    query: str
    found: bool = False
    frn: str = ""
    name: str = ""
    status: str = ""
    permissions: list[str] = field(default_factory=list)
    disciplinary: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def _headers() -> dict[str, str]:
    email = env_key("FCA_AUTH_EMAIL")
    key = env_key("FCA_API_KEY")
    if not email or not key:
        return {}
    return {"X-Auth-Email": email, "X-Auth-Key": key}


def search_firm(name: str) -> FcaResult:
    """Search FCA register by company name (partial match)."""
    out = FcaResult(query=name)
    hdrs = _headers()
    if not hdrs:
        out.error = "FCA_API_KEY o FCA_AUTH_EMAIL mancanti"
        return out
    try:
        data = get_json(f"{BASE}/Search", headers=hdrs, params={"q": name, "type": "firm"})
    except RuntimeError as exc:
        out.error = str(exc)
        return out
    hits = _extract_hits(data)
    if not hits:
        out.notes.append("Nessuna corrispondenza FCA")
        return out
    best = hits[0]
    frn = str(best.get("Reference Number") or best.get("FRN") or best.get("frn") or "")
    out.found = True
    out.frn = frn
    out.name = str(best.get("Name") or best.get("name") or name)
    out.status = str(best.get("Status") or best.get("status") or "")
    if frn:
        out.permissions = _fetch_permissions(frn, hdrs)
        out.disciplinary = _fetch_disciplinary(frn, hdrs)
    return out


def _extract_hits(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("Data", "data", "Results", "results", "Firms", "firms"):
        block = data.get(key)
        if isinstance(block, list):
            return [x for x in block if isinstance(x, dict)]
    if "Name" in data or "name" in data:
        return [data]
    return []


def _fetch_permissions(frn: str, hdrs: dict[str, str]) -> list[str]:
    try:
        data = get_json(f"{BASE}/Firm/{frn}/Permissions", headers=hdrs)
    except RuntimeError:
        return []
    rows = _extract_hits(data)
    out: list[str] = []
    for row in rows[:12]:
        label = row.get("Permission") or row.get("Description") or row.get("Name")
        if label:
            out.append(str(label))
    return out


def _fetch_disciplinary(frn: str, hdrs: dict[str, str]) -> list[str]:
    for path in (f"{BASE}/Firm/{frn}/DisciplinaryHistory", f"{BASE}/Firm/{frn}/Disciplinary"):
        try:
            data = get_json(path, headers=hdrs)
        except RuntimeError:
            continue
        rows = _extract_hits(data)
        if rows:
            return [str(r.get("Description") or r.get("Type") or r)[:120] for r in rows[:5]]
    return []
