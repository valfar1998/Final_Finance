"""ESMA registers — sanctions (Solr) + FIRDS instrument lookup."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finance_alert.regulatory.base import get_json

SANCTIONS_URL = "https://registers.esma.europa.eu/solr/esma_registers_sanctions/select"
FIRDS_URL = "https://registers.esma.europa.eu/solr/esma_registers_firds/select"


@dataclass
class EsmaSanction:
    entity: str
    framework: str
    nature: str
    date: str
    member_state: str = ""


@dataclass
class EsmaResult:
    query: str
    sanctions: list[EsmaSanction] = field(default_factory=list)
    instruments: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def check_entity(name_or_lei: str, *, rows: int = 20) -> EsmaResult:
    """Cerca sanzioni ESMA e strumenti FIRDS per nome o LEI."""
    out = EsmaResult(query=name_or_lei)
    q = name_or_lei.replace('"', "")
    try:
        sdata = get_json(
            SANCTIONS_URL,
            params={
                "q": f"sn_entityName:*{q}*",
                "rows": str(rows),
                "wt": "json",
            },
        )
        out.sanctions = _parse_sanctions(sdata)
    except RuntimeError as exc:
        out.notes.append(f"Sanctions: {exc}")
    try:
        fdata = get_json(
            FIRDS_URL,
            params={
                "q": f"issuerFullName:*{q}* OR isin:*{q}*",
                "rows": str(rows),
                "wt": "json",
            },
        )
        out.instruments = _parse_firds(fdata)
    except RuntimeError as exc:
        out.notes.append(f"FIRDS: {exc}")
    if not out.sanctions and not out.instruments:
        out.notes.append("Nessun record ESMA trovato")
    return out


def _parse_sanctions(data: Any) -> list[EsmaSanction]:
    docs = []
    if isinstance(data, dict):
        block = data.get("response") or {}
        if isinstance(block, dict):
            docs = block.get("docs") or []
    out: list[EsmaSanction] = []
    for row in docs:
        if not isinstance(row, dict):
            continue
        out.append(
            EsmaSanction(
                entity=str(row.get("sn_entityName") or row.get("entityName") or ""),
                framework=str(row.get("sn_sanctionLegalFrameworkName") or ""),
                nature=str(row.get("sn_sanctionNatureName") or row.get("sn_sanctionType") or ""),
                date=str(row.get("sn_sanctionDate") or row.get("sn_publicationDate") or ""),
                member_state=str(row.get("sn_memberState") or ""),
            )
        )
    return out


def _parse_firds(data: Any) -> list[dict]:
    docs = []
    if isinstance(data, dict):
        block = data.get("response") or {}
        if isinstance(block, dict):
            docs = block.get("docs") or []
    out: list[dict] = []
    for row in docs:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "isin": row.get("isin"),
                "name": row.get("issuerFullName") or row.get("financialInstrumentName"),
                "mic": row.get("mic"),
                "lei": row.get("issuerLei"),
            }
        )
    return out
