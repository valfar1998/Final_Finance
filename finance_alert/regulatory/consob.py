"""Italy CONSOB — public registers (HTML parsing, no official open API)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from finance_alert.regulatory.base import get_text

# Elenco imprese di investimento autorizzate (pagina pubblica)
AUTHORIZED_URL = (
    "https://www.consob.it/web/consob/operatori/intermediari/imprese-di-investimento-autorizzate"
)
# Siti oscurati / avvisi
WARNINGS_URL = "https://www.consob.it/web/consob/comunicazione/avvisi"


@dataclass
class ConsobEntry:
    name: str
    kind: str = ""
    note: str = ""


@dataclass
class ConsobResult:
    query: str
    authorized: list[ConsobEntry] = field(default_factory=list)
    warnings: list[ConsobEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def check_company(name: str) -> ConsobResult:
    """Verifica se un intermediario compare negli elenchi pubblici CONSOB."""
    out = ConsobResult(query=name)
    needle = name.lower()[:6]
    try:
        html = get_text(AUTHORIZED_URL)
        for line in re.findall(r">([^<]{4,120})<", html):
            clean = re.sub(r"\s+", " ", line).strip()
            if needle in clean.lower() and len(clean) > 5:
                out.authorized.append(ConsobEntry(name=clean, kind="impresa_investimento"))
    except RuntimeError as exc:
        out.notes.append(f"Albo: {exc}")
    try:
        warn_html = get_text(WARNINGS_URL)
        for line in re.findall(r">([^<]{4,120})<", warn_html):
            clean = re.sub(r"\s+", " ", line).strip()
            if needle in clean.lower():
                out.warnings.append(ConsobEntry(name=clean, kind="avviso/oscuramento"))
    except RuntimeError as exc:
        out.notes.append(f"Avvisi: {exc}")
    if not out.authorized and not out.warnings:
        out.notes.append("Nessuna corrispondenza CONSOB (titolo quotato ≠ intermediario)")
    return out
