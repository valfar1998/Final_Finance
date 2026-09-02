"""Germany BaFin — company register (HTML search, no official bulk API)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from finance_alert.regulatory.base import get_text

SEARCH_URL = "https://portal.mvp.bafin.de/database/InstInfo/institutDetails.do"
# Pagina elenco categorie (Excel export per categoria via UI)
LIST_URL = "https://www.bafin.de/DE/PublikationenDaten/Datenbanken/Datenbanken_node.html"


@dataclass
class BafinCompany:
    name: str
    category: str = ""
    reference: str = ""
    status: str = ""


@dataclass
class BafinResult:
    query: str
    companies: list[BafinCompany] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def search_company(name: str) -> BafinResult:
    """
    Ricerca euristica sul portale BaFin.
    BaFin non espone API REST pubblica: usiamo la pagina di ricerca istituti.
    """
    out = BafinResult(query=name)
    try:
        html = get_text(
            "https://portal.mvp.bafin.de/database/InstInfo/sucheForm.do",
            params={"institutName": f"*{name}*"},
        )
    except RuntimeError as exc:
        out.error = str(exc)
        out.notes.append("BaFin: usa export Excel manuale da bafin.de se serve bulk")
        return out
    # Estrae righe tabella risultati (pattern generico)
    for match in re.finditer(
        r"<td[^>]*>\s*([^<]{3,120}?)\s*</td>\s*<td[^>]*>\s*([^<]{2,80}?)\s*</td>",
        html,
        re.I | re.S,
    ):
        cname = re.sub(r"\s+", " ", match.group(1)).strip()
        cat = re.sub(r"\s+", " ", match.group(2)).strip()
        if name.lower()[:4] in cname.lower():
            out.companies.append(BafinCompany(name=cname, category=cat))
    if not out.companies:
        out.notes.append("Nessun istituto BaFin trovato (verifica nome tedesco/LEI)")
    return out
