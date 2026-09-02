"""France AMF — Info-Financière via OpenDataSoft Explore API v2.1 (gratis)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finance_alert.regulatory.base import get_json

# Portale ufficiale info-financiere.gouv.fr (OpenDataSoft)
BASE = "https://info-financiere.gouv.fr/api/explore/v2.1/catalog/datasets"
DATASET = "info-financiere"


@dataclass
class AmfDocument:
    title: str
    company: str
    doc_type: str
    published: str
    url: str = ""


@dataclass
class AmfResult:
    query: str
    documents: list[AmfDocument] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def search_company(name_or_isin: str, *, limit: int = 10) -> AmfResult:
    """Cerca documenti regolamentati AMF per nome società o ISIN."""
    out = AmfResult(query=name_or_isin)
    q = name_or_isin.replace("'", " ")
    where = f"search(denomination, \"{q}\") OR search(isin, \"{q}\")"
    url = f"{BASE}/{DATASET}/records"
    try:
        data = get_json(url, params={"where": where, "limit": str(limit), "order_by": "date_publication desc"})
    except RuntimeError as exc:
        # Fallback dataset alternativo su portale DILA/AMF
        try:
            alt = "https://dilaamf.opendatasoft.com/api/explore/v2.1/catalog/datasets/info-financiere/records"
            data = get_json(alt, params={"where": where, "limit": str(limit)})
        except RuntimeError:
            out.error = str(exc)
            return out
    rows = data.get("results") if isinstance(data, dict) else []
    if not isinstance(rows, list):
        out.notes.append("Risposta AMF non standard")
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.documents.append(
            AmfDocument(
                title=str(row.get("titre") or row.get("title") or row.get("intitule") or ""),
                company=str(row.get("denomination") or row.get("company") or ""),
                doc_type=str(row.get("type_d_information") or row.get("type") or ""),
                published=str(row.get("date_publication") or row.get("date") or ""),
                url=str(row.get("url") or row.get("lien") or ""),
            )
        )
    if not out.documents:
        out.notes.append("Nessun documento AMF trovato")
    return out
