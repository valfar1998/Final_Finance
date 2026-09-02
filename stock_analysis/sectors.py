#!/usr/bin/env python3
"""Settori e metriche chiave per lo scoring adattivo."""
from __future__ import annotations

# Nomi canonici (dropdown UI)
SECTORS = (
    "REIT",
    "BDC",
    "FINANCIALS",
    "TECH",
    "ENERGY",
    "HEALTHCARE",
    "CONSUMER",
    "INDUSTRIAL",
    "COMMUNICATION",
    "GENERICO",
)

# Alias accettati in input
SECTOR_ALIASES = {
    "BANCA": "FINANCIALS",
    "BANK": "FINANCIALS",
    "BANKS": "FINANCIALS",
    "FINANCIAL": "FINANCIALS",
    "ENERGY & UTILITIES": "ENERGY",
    "ENERGY_UTILITIES": "ENERGY",
    "UTILITIES": "ENERGY",
    "UTILITY": "ENERGY",
    "HEALTH": "HEALTHCARE",
    "HEALTH CARE": "HEALTHCARE",
    "INDUSTRIALS": "INDUSTRIAL",
    "INDUSTRIAL & MATERIALS": "INDUSTRIAL",
    "MATERIALS": "INDUSTRIAL",
    "COMMUNICATIONS": "COMMUNICATION",
    "COMMS": "COMMUNICATION",
    "TELECOM": "COMMUNICATION",
    "MEDIA": "COMMUNICATION",
}

SECTOR_LABELS = {
    "REIT": "REIT",
    "BDC": "BDC",
    "FINANCIALS": "Financials (banche/assicurazioni)",
    "TECH": "Tech / Software / SaaS",
    "ENERGY": "Energy & Utilities",
    "HEALTHCARE": "Healthcare / Pharma / Biotech",
    "CONSUMER": "Consumer (retail/brand)",
    "INDUSTRIAL": "Industrial & Materials",
    "COMMUNICATION": "Communication / Media / Telecom",
    "GENERICO": "Generico / multi-settore",
}

SECTOR_KEY_METRICS: dict[str, list[str]] = {
    "REIT": [
        "FFO / AFFO (non EPS)",
        "NAV Premium/Discount",
        "Debt/EBITDA + Interest Coverage",
        "Same-Store NOI Growth",
        "Dividend Yield (su FFO)",
    ],
    "BDC": [
        "NII (Net Investment Income)",
        "NAV per share + Premium/Discount",
        "Non-Accrual Rate",
        "Dividend Coverage (NII/Dividendo)",
        "Debt/Equity (limite regolamentare)",
    ],
    "FINANCIALS": [
        "CET1 / Tier 1 Capital Ratio",
        "ROE + ROA",
        "NIM (Net Interest Margin)",
        "Cost/Income Ratio",
        "NPL Ratio + Provision Coverage",
    ],
    "TECH": [
        "Revenue Growth (YoY, 3yr)",
        "Gross Margin + FCF Margin",
        "R&D / Revenue",
        "Rule of 40 (Growth% + FCF Margin%)",
        "Net Revenue Retention (SaaS)",
    ],
    "ENERGY": [
        "EV/EBITDA (non P/E)",
        "Debt/EBITDA + Interest Coverage",
        "FFO / Debt",
        "Dividend Yield + Payout sostenibilità",
        "Reserve Life / Capacity Factor",
    ],
    "HEALTHCARE": [
        "Gross Margin (brevetti)",
        "R&D / Revenue",
        "Pipeline NPV / Market Cap",
        "Patent Cliff (anni rimasti)",
        "FDA / regulatory risk",
    ],
    "CONSUMER": [
        "Same-Store Sales",
        "Gross & Operating Margin",
        "Inventory Turnover",
        "Pricing Power / Brand Moat",
        "FCF Conversion",
    ],
    "INDUSTRIAL": [
        "Order Backlog / Book-to-Bill",
        "ROIC",
        "EBITDA Margin",
        "Capex / Revenue",
        "Ciclo (early/late cycle)",
    ],
    "COMMUNICATION": [
        "ARPU + Subscriber Growth + Churn",
        "EBITDA Margin",
        "Capex / Revenue (network)",
        "Content Spend / Revenue (media)",
        "FCF Yield post-capex",
    ],
    "GENERICO": [
        "P/E, EPS, FCF, D/E, growth",
        "Margini e ROE",
        "Dividend sustainability",
        "Consenso analisti",
    ],
}


def normalize_sector(value: str) -> str:
    raw = (value or "").strip().upper()
    if not raw:
        raise ValueError("Settore mancante")
    raw = SECTOR_ALIASES.get(raw, raw)
    if raw not in SECTORS:
        raise ValueError(
            f"Settore non valido: {value!r}. Usa: {', '.join(SECTORS)} "
            f"(alias: BANCA→FINANCIALS, UTILITIES→ENERGY, …)"
        )
    return raw


def sector_metrics_blurb(sector: str) -> str:
    s = normalize_sector(sector)
    keys = SECTOR_KEY_METRICS.get(s, [])
    label = SECTOR_LABELS.get(s, s)
    lines = [f"📌 Metriche chiave — {label}:"]
    for k in keys:
        lines.append(f"   • {k}")
    return "\n".join(lines)
