"""Unified regulatory hub — routes ticker/region to the right authority."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from finance_alert.regulatory.amf import search_company as amf_search
from finance_alert.regulatory.bafin import search_company as bafin_search
from finance_alert.regulatory.consob import check_company as consob_check
from finance_alert.regulatory.esma import check_entity as esma_check
from finance_alert.regulatory.fca import search_firm as fca_search
from finance_alert.regulatory.fsa_edinet import filings_for_ticker as edinet_filings
from finance_alert.regulatory.opendart import filings_for_ticker as opendart_filings

# Suffissi Yahoo → giurisdizione primaria (espanso multi-mercato)
_SUFFIX_REGION = {
    ".L": "UK",
    ".IL": "UK",
    ".PA": "FR",
    ".DE": "DE",
    ".F": "DE",
    ".MI": "IT",
    ".T": "JP",
    ".TO": "JP",
    ".SW": "CH",
    ".AS": "NL",
    ".MC": "ES",
    ".SA": "BR",
    ".MX": "MX",
    ".HK": "HK",
    ".AX": "AU",
    ".NZ": "NZ",
    ".KS": "KR",
    ".KQ": "KR",
    ".SS": "CN",
    ".SZ": "CN",
    ".NS": "IN",
    ".BO": "IN",
    ".SI": "SG",
    ".ST": "SE",
    ".OL": "NO",
    ".CO": "DK",
    ".HE": "FI",
    ".VI": "AT",
    ".WA": "PL",
    ".BK": "TH",
    ".TW": "TW",
    ".TA": "IL",
    ".JO": "ZA",
    ".ME": "RU",
}


@dataclass
class RegulatoryProfile:
    ticker: str
    region: str
    clean: bool = True
    flags: list[str] = field(default_factory=list)
    sources_checked: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    score_penalty: float = 0.0  # 0..3 subtracted from unified score


def detect_region(ticker: str) -> str:
    t = ticker.upper().strip()
    for suffix, region in _SUFFIX_REGION.items():
        if t.endswith(suffix):
            return region
    if re.match(r"^\d{4}(\.T)?$", t):
        return "JP"
    return "US"


def regulatory_check(ticker: str, company_name: str = "") -> RegulatoryProfile:
    """Run applicable government checks for ticker region."""
    region = detect_region(ticker)
    profile = RegulatoryProfile(ticker=ticker, region=region)
    name = company_name or ticker

    if region == "UK":
        profile.sources_checked.append("FCA")
        fca = fca_search(name)
        profile.details["fca"] = fca.__dict__
        if fca.error:
            profile.flags.append(f"FCA: {fca.error[:60]}")
        elif fca.disciplinary:
            profile.clean = False
            profile.score_penalty += 2.0
            profile.flags.append(f"FCA storico disciplinare ({len(fca.disciplinary)})")

    if region == "FR":
        profile.sources_checked.append("AMF")
        amf = amf_search(name)
        profile.details["amf"] = {"docs": len(amf.documents), "error": amf.error}
        if amf.error:
            profile.flags.append(f"AMF: {amf.error[:60]}")

    if region == "DE":
        profile.sources_checked.append("BaFin")
        bafin = bafin_search(name)
        profile.details["bafin"] = {"hits": len(bafin.companies), "error": bafin.error}
        if bafin.error:
            profile.flags.append(f"BaFin: {bafin.error[:60]}")

    if region == "IT":
        profile.sources_checked.append("CONSOB")
        consob = consob_check(name)
        profile.details["consob"] = {
            "authorized": len(consob.authorized),
            "warnings": len(consob.warnings),
        }
        if consob.warnings:
            profile.clean = False
            profile.score_penalty += 3.0
            profile.flags.append(f"CONSOB avvisi/oscuramenti ({len(consob.warnings)})")

    if region == "JP":
        profile.sources_checked.append("FSA/EDINET")
        edinet = edinet_filings(ticker)
        profile.details["edinet"] = {"filings": len(edinet.filings), "error": edinet.error}
        if edinet.error:
            profile.flags.append(f"EDINET: {edinet.error[:60]}")

    if region == "KR":
        profile.sources_checked.append("OpenDART")
        dart = opendart_filings(ticker)
        profile.details["opendart"] = {
            "disclosures": len(dart.disclosures),
            "corp_code": dart.corp_code,
            "error": dart.error,
        }
        if dart.error:
            profile.flags.append(f"OpenDART: {dart.error[:60]}")
        elif dart.disclosures:
            profile.flags.append(f"OpenDART disclosure recenti ({len(dart.disclosures)})")

    if region in {"CN", "HK"}:
        # Nessuna API governativa REST gratuita tipo EDGAR/OpenDART nel hub;
        # prezzi via Yahoo (.SS/.SZ/.HK); in locale opzionale AKShare.
        profile.sources_checked.append("CN/HK-Yahoo")
        profile.details["asia"] = {
            "note": "Prezzi Yahoo; filings CN locali via AKShare (opzionale in locale)",
        }

    # ESMA copre UE — utile per mercati europei + UK post-Brexit cross-listing
    if region in {"FR", "DE", "IT", "UK", "CH", "NL", "ES", "SE", "NO", "DK", "FI", "AT", "PL"}:
        profile.sources_checked.append("ESMA")
        esma = esma_check(name)
        profile.details["esma"] = {
            "sanctions": len(esma.sanctions),
            "instruments": len(esma.instruments),
        }
        if esma.sanctions:
            profile.clean = False
            profile.score_penalty += min(3.0, len(esma.sanctions))
            profile.flags.append(f"ESMA sanzioni ({len(esma.sanctions)})")

    profile.score_penalty = min(3.0, profile.score_penalty)
    return profile
