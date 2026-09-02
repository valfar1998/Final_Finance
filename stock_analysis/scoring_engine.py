#!/usr/bin/env python3
"""
Scoring locale: estrae metriche da HTML SingleFile e applica lo schema del prompt.
Se i dati critici mancano → verdetto DATI INSUFFICIENTI (niente COMPRA inventata).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Campi minimi per considerare l'analisi affidabile
CRITICAL_FIELDS = (
    "price",
    "pe",
    "eps",
    "market_cap",
    "rev_growth",
    "fcf",
    "de",
)
IMPORTANT_FIELDS = (
    "roe",
    "div_yield",
    "target",
    "pb",
    "gross_m",
    "op_m",
    "beta",
    "inst",
)

# Parole da non confondere con ticker
TICKER_BLOCKLIST = {
    "WHAT", "THIS", "THAT", "WITH", "FROM", "HTTP", "HTTPS", "HTML", "CURRE",
    "PRICE", "STOCK", "SHARE", "QUOTE", "MARKET", "CLOSE", "OPEN", "VOLUME",
    "ABOUT", "AFTER", "BEFORE", "UNDER", "OVER", "NEWS", "HOME", "LOGIN",
    "CHART", "DATA", "YEAR", "WEEK", "DAY", "MONTH", "NULL", "TRUE", "FALSE",
}


def _to_float(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.upper() in {"N/A", "NA", "-", "—", "--", "NONE"}:
        return None
    # (997.65) → negativo
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace(",", "").replace(" ", "").replace("$", "").replace("€", "").replace("¥", "")
    s = s.replace("%", "")
    mult = 1.0
    if s[-1:] in "Kk":
        mult = 1_000
        s = s[:-1]
    elif s[-1:] in "Mm":
        mult = 1_000_000
        s = s[:-1]
    elif s[-1:] in "Bb":
        mult = 1_000_000_000
        s = s[:-1]
    elif s[-1:] in "Tt":
        mult = 1_000_000_000_000
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None


def _parse_money(raw: str | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    s = s.replace(",", "").replace("$", "").replace("€", "").replace("¥", "")
    m = re.search(r"([-+]?\d+(?:\.\d+)?)\s*([KMBTkmbt])?", s)
    if not m:
        return _to_float(s)
    num = float(m.group(1))
    suf = (m.group(2) or "").upper()
    mult = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(suf, 1)
    return num * mult


def find_labeled(text: str, labels: list[str], value_re: str | None = None) -> str | None:
    """Cerca 'Label .... valore' sulla stessa riga (niente match a capo → Market Cap)."""
    if value_re is None:
        # niente \\s prima del suffisso K/M/B/T (altrimenti prende la M di Market Cap)
        value_re = r"(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?(?:[ \t]*[KMBTkmbt])?%?)"
    for label in labels:
        pat = rf"{label}[ \t]*[:\|]?[ \t]*{value_re}"
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1).strip()
        pat2 = rf"{label}[ \t]*\n[ \t]*{value_re}"
        m2 = re.search(pat2, text, re.I)
        if m2:
            return m2.group(1).strip()
    return None


def find_row_numbers(text: str, labels: list[str]) -> list[float]:
    """
    Tabella multi-anno TIKR: 'Free Cash Flow  1200  1800  2577.89'
    Restituisce tutti i numeri sulla riga (esclusi anni tipo 2021).
    """
    for label in labels:
        pat = rf"(?:^|\n)[ \t]*{label}[ \t]*[:\|]?[ \t]*([^\n]{{0,500}})"
        m = re.search(pat, text, re.I | re.M)
        if not m:
            continue
        rest = m.group(1)
        vals: list[float] = []
        for nm in re.finditer(
            r"(\(?-?[0-9][0-9,]*(?:\.[0-9]+)?\)?)[ \t]*([KMBTkmbt])?",
            rest,
        ):
            raw = nm.group(0)
            # salta percentuali
            end = nm.end()
            if end < len(rest) and rest[end : end + 1] == "%":
                continue
            v = _parse_money(raw)
            if v is None:
                continue
            # anni calendario (colonne header residue)
            if 1990 <= v <= 2100 and abs(v - round(v)) < 1e-9:
                continue
            vals.append(v)
        if vals:
            return vals
    return []


def pick_latest_number(text: str, labels: list[str], money: bool = True) -> float | None:
    """Ultimo valore annuale sulla riga (tipicamente l'anno più recente in TIKR)."""
    vals = find_row_numbers(text, labels)
    if vals:
        return vals[-1]
    raw = find_labeled(text, labels)
    if raw is None:
        return None
    return _parse_money(raw) if money else _to_float(raw)


def _detect_millions_scale(text: str) -> float:
    """TIKR Cash Flow spesso in Millions → moltiplica per 1e6 se dichiarato."""
    head = text[:3000]
    if re.search(
        r"(?i)(?:USD|CNY|EUR|GBP|JPY|HKD)?\s*(?:in\s+)?millions\b|\(millions\)|\bmm\b|\b000,?000\b",
        head,
    ):
        return 1_000_000.0
    if re.search(r"(?i)(?:in\s+)?thousands\b|\(thousands\)", head):
        return 1_000.0
    if re.search(r"(?i)(?:in\s+)?billions\b|\(billions\)", head):
        return 1_000_000_000.0
    return 1.0


def _scale_statement_value(val: float | None, scale: float, mcap: float | None = None) -> float | None:
    if val is None:
        return None
    scaled = val * scale
    # Se ancora minuscolo rispetto al market cap, prova milioni impliciti
    if mcap and mcap > 1e8 and abs(scaled) > 0 and abs(scaled) < mcap * 1e-5 and abs(scaled) < 1e7:
        trial = scaled * 1_000_000.0
        y = abs(trial / mcap) * 100
        if 0.05 <= y <= 80:
            return trial
    return scaled


def extract_cashflow_block(blobs: list[tuple[str, str]]) -> dict[str, float | None]:
    """
    Estrae OCF / CapEx / FCF da Cash Flow Statement o Estimates (TIKR).
    Preferisce la riga Free Cash Flow; altrimenti FCF = OCF − |CapEx|.
    """
    ocf_labels = [
        r"Cash From Operations",
        r"Cash from Operating Activities",
        r"Cash From Operating Activities",
        r"Total Cash from Operating Activities",
        r"Net Cash from Operating Activities",
        r"Operating Cash Flow \(ttm\)",
        r"Operating Cash Flow",
        r"Cash Flow from Operations",
        r"\bCFO\b",
    ]
    capex_labels = [
        r"Purchase[s]? Of Property Plant And Equipment",
        r"Purchase[s]? of PPE",
        r"Purchase[s]? of Fixed Assets",
        r"Capital Expenditures?",
        r"Capital Expenditure",
        r"Capex",
        r"CapEx",
        r"PP&E Purchases",
    ]
    fcf_labels = [
        r"Levered Free Cash Flow \(ttm\)",
        r"Unlevered Free Cash Flow",
        r"Free Cash Flow \(ttm\)",
        r"Free Cash Flow",
        r"\bFCF\b",
    ]

    section_headers = [
        r"Cash Flow Statement",
        r"Statement of Cash Flows",
        r"Cash Flows Statement",
        r"Cash Flow",
        r"PRIORITY: CASH FLOW",
        r"Estimates",
        r"Financial Estimates",
        r"Forward Estimates",
    ]

    out: dict[str, float | None] = {
        "ocf": None,
        "capex": None,
        "fcf": None,
        "fcf_source": None,  # type: ignore[assignment]
    }

    for _name, body in blobs:
        if not body:
            continue
        # Prima sezioni mirate (finestre ampie: TIKR è verboso)
        texts_to_scan = []
        for h in section_headers:
            sec = section(body, [h], max_chars=120_000)
            if sec:
                texts_to_scan.append(sec)
        texts_to_scan.append(body)

        for blob in texts_to_scan:
            scale = _detect_millions_scale(blob)
            ocf = pick_latest_number(blob, ocf_labels)
            capex = pick_latest_number(blob, capex_labels)
            fcf = pick_latest_number(blob, fcf_labels)

            # CapEx in CF spesso negativo: normalizza a uscito positivo
            capex_abs = abs(capex) if capex is not None else None

            if fcf is None and ocf is not None and capex_abs is not None:
                fcf = ocf - capex_abs
                src = "ocf-capex"
            elif fcf is not None:
                src = "fcf-row"
            else:
                src = None

            if ocf is not None and out["ocf"] is None:
                out["ocf"] = _scale_statement_value(ocf, scale)
            if capex_abs is not None and out["capex"] is None:
                out["capex"] = _scale_statement_value(capex_abs, scale)
            if fcf is not None and out["fcf"] is None:
                out["fcf"] = _scale_statement_value(fcf, scale)
                out["fcf_source"] = src  # type: ignore[assignment]

            if out["fcf"] is not None and out["ocf"] is not None:
                return out

    # Ultimo fallback: FCF = OCF - CapEx se raccolti da pezzi diversi
    if out["fcf"] is None and out["ocf"] is not None and out["capex"] is not None:
        out["fcf"] = out["ocf"] - out["capex"]
        out["fcf_source"] = "ocf-capex"  # type: ignore[assignment]
    return out


def _sanitize_share_metric(val: float | None, max_abs: float = 1000.0) -> float | None:
    """EPS/P/E per-share: scarta valori assurdi da parsing HTML."""
    if val is None:
        return None
    if abs(val) > max_abs:
        return None
    return val


def section(text: str, headers: list[str], max_chars: int = 8000) -> str:
    """Estrae un pezzo di testo dopo un header (per limitare falsi positivi)."""
    for h in headers:
        m = re.search(rf"{h}(.{{0,{max_chars}}})", text, re.I | re.S)
        if m:
            return m.group(0)
    return ""


def extract_metrics(
    investing: str,
    tikr: str,
    yahoo_metrics: dict[str, Any] | None = None,
    extra_sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Estrae da HTML Investing/TIKR (+ fonti extra); Yahoo API (se presente) ha priorità."""
    blobs = []
    # Priorità: TIKR → Investing → altre HTML (riempiono i buchi)
    for name, body in (("tikr", tikr), ("investing", investing)):
        if body and body.strip() and body.strip().lower() != "non disponibile":
            blobs.append((name, body))
    if extra_sources:
        for name, body in extra_sources.items():
            if body and body.strip() and body.strip().lower() != "non disponibile":
                blobs.append((name, body))

    def pick(labels: list[str], money: bool = False, sources: list[str] | None = None) -> float | None:
        for name, body in blobs:
            if sources and name not in sources:
                continue
            raw = find_labeled(body, labels)
            if raw is None:
                continue
            val = _parse_money(raw) if money else _to_float(raw)
            if val is not None:
                return val
        return None

    def pick_in_section(headers: list[str], labels: list[str], money: bool = False) -> float | None:
        for name, body in blobs:
            sec = section(body, headers)
            if not sec:
                continue
            raw = find_labeled(sec, labels)
            if raw is None:
                continue
            val = _parse_money(raw) if money else _to_float(raw)
            if val is not None:
                return val
        return None

    # --- Identità ---
    ticker = None
    for name, body in blobs:
        for pat in (
            r"finance\.yahoo\.com/quote/([A-Z]{1,5})(?:[/?\"']|$)",
            r"nasdaq\.com/market-activity/stocks/([a-z]{1,5})",
            r"\(([A-Z]{1,5})\)\s*(?:Stock Price|Add to Watchlist|Summary)",
            r"Symbol[:\s]+([A-Z]{1,5})\b",
        ):
            m = re.search(pat, body, re.I)
            if m:
                cand = m.group(1).upper()
                if cand not in TICKER_BLOCKLIST and cand.isalpha():
                    ticker = cand
                    break
        if ticker:
            break

    name_co = None
    for _, body in blobs:
        m = re.search(
            r"([A-Za-z0-9][A-Za-z0-9&.\- ]{1,50}?)\s*\(([A-Z]{1,5})\)\s*(?:Stock|Quote|Common Stock)",
            body,
        )
        if m and m.group(1).lower() not in {"what is the", "what is"}:
            title = m.group(1).strip()
            if not title.lower().startswith("what "):
                name_co = title
                if not ticker:
                    cand = m.group(2).upper()
                    if cand not in TICKER_BLOCKLIST:
                        ticker = cand
                break

    price = pick(
        [
            r"Previous Close",
            r"Prezzo precedente",
            r"regularMarketPreviousClose",
            r"Last Price",
            r"Ultimo",
        ]
    )
    # Yahoo quote often has big price near top — only if still missing, try careful pattern
    if price is None:
        for _, body in blobs:
            m = re.search(r"(?:At close|In chiusura)[:\s]*\$?\s*([0-9]+(?:\.[0-9]+)?)", body, re.I)
            if m:
                price = _to_float(m.group(1))
                break

    mcap = pick(
        [r"Market Cap(?:italization)?", r"Cap\.?\s*di mercato", r"Market capitalisation"],
        money=True,
    )

    pe = pick([r"Trailing P/E", r"P/E \(TTM\)", r"PE Ratio \(TTM\)", r"Price/Earnings \(TTM\)"])
    pe = _sanitize_share_metric(pe, 500)

    forward_pe = _sanitize_share_metric(pick([r"Forward P/E", r"Forward PE"]), 500)
    peg = pick([r"PEG Ratio \(5 yr expected\)", r"PEG Ratio"])
    if peg is not None and (peg <= 0 or peg > 20):
        peg = None

    pb = _sanitize_share_metric(pick([r"Price/Book \(mrq\)", r"Price/Book", r"P/B"]), 100)
    ps = pick([r"Price/Sales \(ttm\)", r"Price/Sales", r"P/S"])
    if ps is not None and (ps <= 0 or ps > 200):
        ps = None
    ev_ebitda = _sanitize_share_metric(pick([r"Enterprise Value/EBITDA", r"EV/EBITDA"]), 200)

    eps = _sanitize_share_metric(
        pick([r"Diluted EPS \(ttm\)", r"EPS \(TTM\)", r"Trailing EPS"]),
        1000,
    )
    forward_eps = _sanitize_share_metric(pick([r"EPS Estimate Next Year", r"Forward EPS"]), 1000)
    eps_growth = pick([r"Quarterly Earnings Growth \(yoy\)", r"EPS Growth YoY", r"Earnings Growth"])

    de = pick([r"Total Debt/Equity \(mrq\)", r"Debt/Equity", r"Total Debt to Equity"])
    if de is not None and de > 5:  # Yahoo a volte in %
        de = de / 100.0

    current_ratio = pick([r"Current Ratio \(mrq\)", r"Current Ratio"])
    interest_cov = pick([r"Interest Coverage", r"Times Interest Earned"])
    altman = pick([r"Altman Z-Score", r"Altman Z Score"])

    # Cash Flow: prima TIKR statement/estimates (ultimo anno), poi label semplici
    cf = extract_cashflow_block(blobs)
    fcf = cf.get("fcf")
    ocf = cf.get("ocf")
    capex = cf.get("capex")
    fcf_source = cf.get("fcf_source")
    if fcf is None:
        fcf = pick(
            [r"Levered Free Cash Flow \(ttm\)", r"Free Cash Flow \(ttm\)", r"Free Cash Flow"],
            money=True,
        )
    if ocf is None:
        ocf = pick([r"Operating Cash Flow \(ttm\)", r"Operating Cash Flow", r"Cash From Operations"], money=True)
    if fcf is None and ocf is not None and capex is not None:
        fcf = ocf - abs(capex)
        fcf_source = "ocf-capex"
    net_income = pick(
        [r"Net Income Avi to Common \(ttm\)", r"Net Income \(ttm\)", r"Net Income"],
        money=True,
    )

    div_yield = pick(
        [
            r"Trailing Annual Dividend Yield",
            r"Forward Dividend & Yield",
            r"Dividend Yield",
            r"Yield",
        ]
    )
    # Forward Dividend & Yield often "0.80 (0.25%)" — already handled if % captured; clamp absurd
    if div_yield is not None and div_yield > 30:
        div_yield = None

    payout = pick([r"Payout Ratio"])

    rev_growth = pick([r"Quarterly Revenue Growth \(yoy\)", r"Revenue Growth YoY", r"Revenue Growth"])
    rev_cagr_3y = pick([r"Revenue CAGR 3Y", r"Revenue Growth 3Y"])

    gross_m = pick([r"Gross Margin \(ttm\)", r"Gross Profit Margin", r"Gross Margin"])
    op_m = pick([r"Operating Margin \(ttm\)", r"Operating Margin"])
    net_m = pick([r"Profit Margin", r"Net Profit Margin", r"Net Margin"])
    roe = pick([r"Return on Equity \(ttm\)", r"Return on Equity", r"ROE"])
    roa = pick([r"Return on Assets \(ttm\)", r"Return on Assets", r"ROA"])

    # Sanity margins: if op_m ≈ gross_m suspiciously and no yahoo stats, keep but flag later
    beta = pick([r"Beta \(5Y Monthly\)", r"Beta \(5Y\)", r"Beta"])
    sma50 = pick([r"50-Day Moving Average", r"50-Day Average"])
    sma200 = pick([r"200-Day Moving Average", r"200-Day Average"])
    rsi = pick([r"RSI \(14\)", r"RSI 14", r"RSI"])
    if rsi is not None and (rsi < 0 or rsi > 100):
        rsi = None

    week52 = pick([r"52-Week Change", r"52 Week Change", r"52-Week Change \(from 52W Low\)"])
    avg_vol = pick([r"Avg\. Volume", r"Average Volume", r"Avg Volume"], money=True)

    target = pick_in_section(
        [r"Analyst Price Targets", r"1y Target Est", r"Average Target Price", r"Analyst Targets"],
        [r"Average", r"Avg\.?", r"Mean", r"1y Target Est", r"Target"],
    )
    if target is None:
        target = pick([r"1y Target Est", r"Average Target Price"])

    target_low = pick_in_section([r"Analyst Price Targets", r"Price Target"], [r"Low"])
    target_high = pick_in_section([r"Analyst Price Targets", r"Price Target"], [r"High"])

    # Analisti: SOLO nella sezione recommendation (evita 2011 falsi)
    strong_buy = buy = hold = sell = strong_sell = n_analysts = None
    for _, body in blobs:
        sec = section(
            body,
            [
                r"Analyst Recommendations",
                r"Recommendation Trends",
                r"Analyst Rating",
                r"Upgrades.?Downgrades",
            ],
            max_chars=5000,
        )
        if not sec:
            continue
        def cnt(lab: str) -> float | None:
            raw = find_labeled(sec, [lab])
            v = _to_float(raw) if raw else None
            if v is not None and 0 <= v <= 80:
                return v
            return None

        sb = cnt(r"Strong Buy")
        b = cnt(r"(?<!Strong )Buy")
        h = cnt(r"Hold")
        s = cnt(r"(?<!Strong )Sell")
        ss = cnt(r"Strong Sell")
        if any(x is not None for x in (sb, b, h, s, ss)):
            strong_buy, buy, hold, sell, strong_sell = sb or 0, b or 0, h or 0, s or 0, ss or 0
            n_analysts = strong_buy + buy + hold + sell + strong_sell
            if n_analysts > 80 or n_analysts < 1:
                strong_buy = buy = hold = sell = strong_sell = n_analysts = None
            else:
                break

    # Number of Analyst Opinion
    if n_analysts is None:
        n_raw = pick([r"No\. of Analysts", r"Number of Analysts", r"Analyst Count"])
        if n_raw is not None and 1 <= n_raw <= 80:
            n_analysts = n_raw

    inst = pick([r"% Held by Institutions", r"Institutions Held", r"Institutional Ownership"])
    if inst is not None and inst > 100:
        inst = None
    short_pct = pick([r"Short % of Float", r"Short Percent of Float", r"Short Interest \(%\)"])
    short_ratio = pick([r"Short Ratio", r"Days to Cover"])

    ffo = pick([r"FFO/Share", r"FFO per Share", r"FFO"])
    affo = pick([r"AFFO/Share", r"AFFO per Share", r"AFFO"])
    nav = pick([r"NAV/Share", r"NAV per Share", r"Net Asset Value"])
    debt_ebitda = pick([r"Debt/EBITDA", r"Net Debt/EBITDA"])
    nii = pick([r"NII/Share", r"Net Investment Income", r"NII"])
    cet1 = pick([r"CET1 Ratio", r"CET1", r"Tier 1 Capital Ratio", r"Tier 1 Ratio"])
    nim = pick([r"Net Interest Margin", r"NIM"])
    npl = pick([r"Non-Performing Loans", r"NPL Ratio", r"NPL"])
    bvps = pick([r"Book Value Per Share", r"Book Value/Share", r"Book/sh"])
    shares = pick([r"Shares Outstanding", r"Shares Out"], money=True)

    # Metriche settoriali extra (spesso da TIKR / report)
    ss_noi = pick([r"Same[- ]Store NOI", r"SS NOI Growth", r"Same Store NOI"])
    ss_sales = pick([r"Same[- ]Store Sales", r"Comparable Store Sales", r"Comp Sales"])
    non_accrual = pick([r"Non[- ]Accrual", r"Nonaccrual Rate", r"Non-Accruals"])
    nii_coverage = pick([r"NII Coverage", r"Dividend Coverage", r"NII / Dividend"])
    cost_income = pick([r"Cost[/ ]Income", r"Cost to Income", r"Efficiency Ratio"])
    rd_rev = pick([r"R&D[/ ]Revenue", r"Research and Development.*Revenue", r"R&D %"])
    roic = pick([r"ROIC", r"Return on Invested Capital"])
    book_to_bill = pick([r"Book[- ]to[- ]Bill", r"Book to Bill", r"Backlog"])
    capex_rev = pick([r"Capex[/ ]Revenue", r"Capital Expenditure.*Revenue", r"CapEx %"])
    arpu = pick([r"ARPU", r"Average Revenue Per User"])
    churn = pick([r"Churn", r"Churn Rate"])
    inventory_turns = pick([r"Inventory Turnover", r"Inventory Turns"])
    revenue = pick([r"Total Revenue \(ttm\)", r"Revenue \(ttm\)", r"Total Revenue"], money=True)
    ebitda = pick([r"EBITDA", r"Normalized EBITDA"], money=True)
    ebitda_m = pick([r"EBITDA Margin", r"EBITDA Margin \(ttm\)"])
    fcf_margin = pick([r"FCF Margin", r"Free Cash Flow Margin"])
    nrr = pick([r"Net Revenue Retention", r"NRR", r"Net Retention"])

    # Coerenza prezzo / market cap (prima del merge Yahoo)
    if price is not None and (price <= 0 or price > 100_000):
        price = None
    if mcap is not None and mcap < 1e6:
        mcap = None

    out: dict[str, Any] = {
        "ticker": ticker or "N/D",
        "name": name_co or "N/D",
        "price": price,
        "market_cap": mcap,
        "pe": pe,
        "forward_pe": forward_pe,
        "peg": peg,
        "pb": pb,
        "ps": ps,
        "ev_ebitda": ev_ebitda,
        "eps": eps,
        "forward_eps": forward_eps,
        "eps_growth": eps_growth,
        "de": de,
        "current_ratio": current_ratio,
        "interest_cov": interest_cov,
        "altman": altman,
        "fcf": fcf,
        "ocf": ocf,
        "capex": capex,
        "fcf_source": fcf_source,
        "net_income": net_income,
        "revenue": revenue,
        "ebitda": ebitda,
        "ebitda_m": ebitda_m,
        "fcf_margin": fcf_margin,
        "div_yield": div_yield,
        "payout": payout,
        "rev_growth": rev_growth,
        "rev_cagr_3y": rev_cagr_3y,
        "gross_m": gross_m,
        "op_m": op_m,
        "net_m": net_m,
        "roe": roe,
        "roa": roa,
        "beta": beta,
        "sma50": sma50,
        "sma200": sma200,
        "rsi": rsi,
        "week52": week52,
        "avg_vol": avg_vol,
        "target": target,
        "target_low": target_low,
        "target_high": target_high,
        "strong_buy": strong_buy,
        "buy": buy,
        "hold": hold,
        "sell": sell,
        "strong_sell": strong_sell,
        "n_analysts": n_analysts,
        "inst": inst,
        "short_pct": short_pct,
        "short_ratio": short_ratio,
        "ffo": ffo,
        "affo": affo,
        "nav": nav,
        "debt_ebitda": debt_ebitda,
        "nii": nii,
        "nii_coverage": nii_coverage,
        "non_accrual": non_accrual,
        "ss_noi": ss_noi,
        "ss_sales": ss_sales,
        "cet1": cet1,
        "nim": nim,
        "npl": npl,
        "cost_income": cost_income,
        "rd_rev": rd_rev,
        "roic": roic,
        "book_to_bill": book_to_bill,
        "capex_rev": capex_rev,
        "arpu": arpu,
        "churn": churn,
        "inventory_turns": inventory_turns,
        "nrr": nrr,
        "bvps": bvps,
        "shares": shares,
    }

    # Yahoo API: riempie i buchi. Eccezione FCF/OCF: se Yahoo manca, resta TIKR/HTML.
    # Non sovrascrivere FCF HTML con None (già skippato); se Yahoo ha FCF lo usa.
    html_fcf = out.get("fcf")
    html_ocf = out.get("ocf")
    html_capex = out.get("capex")
    html_fcf_source = out.get("fcf_source")

    if yahoo_metrics:
        for k, v in yahoo_metrics.items():
            if k.startswith("_") or v is None:
                continue
            # Non far perdere CapEx/FCF_source HTML già estratti
            if k == "fcf_source":
                continue
            if k == "capex" and out.get("capex") is not None:
                continue
            out[k] = v

    # Regola: Se Yahoo non fornisce FCF → usa TIKR Cash Flow / OCF−CapEx
    if out.get("fcf") is None and html_fcf is not None:
        out["fcf"] = html_fcf
        out["fcf_source"] = html_fcf_source or "tikr"
    if out.get("ocf") is None and html_ocf is not None:
        out["ocf"] = html_ocf
    if out.get("capex") is None and html_capex is not None:
        out["capex"] = html_capex

    # Ultimo fallback post-merge Yahoo
    if out.get("fcf") is None and out.get("ocf") is not None and out.get("capex") is not None:
        out["fcf"] = out["ocf"] - abs(out["capex"])
        out["fcf_source"] = "ocf-capex"

    # Scala statement values se ancora troppo piccoli vs market cap
    mcap_pre = out.get("market_cap")
    for key in ("fcf", "ocf", "capex"):
        out[key] = _scale_statement_value(out.get(key), 1.0, mcap_pre)

    # Derivati post-merge
    fcf = out.get("fcf")
    mcap = out.get("market_cap")
    net_income = out.get("net_income")
    revenue = out.get("revenue")
    out["fcf_yield"] = (fcf / mcap) * 100 if fcf is not None and mcap and mcap > 0 else None
    out["fcf_ni"] = (fcf / net_income) if fcf is not None and net_income and abs(net_income) > 0 else None
    if out.get("fcf_margin") is None and fcf is not None and revenue and revenue > 0:
        out["fcf_margin"] = (fcf / revenue) * 100
    if out.get("ebitda_m") is None and out.get("ebitda") is not None and revenue and revenue > 0:
        out["ebitda_m"] = (out["ebitda"] / revenue) * 100
    if out.get("rule_of_40") is None and out.get("rev_growth") is not None and out.get("fcf_margin") is not None:
        out["rule_of_40"] = out["rev_growth"] + out["fcf_margin"]
    if out.get("nav") and out.get("price"):
        out["nav_premium"] = (out["price"] / out["nav"] - 1) * 100
    else:
        out.setdefault("nav_premium", None)

    if out.get("price") is not None and (out["price"] <= 0 or out["price"] > 100_000):
        out["price"] = None
    if out.get("market_cap") is not None and out["market_cap"] < 1e6:
        out["market_cap"] = None

    return out


def data_coverage(m: dict) -> dict[str, Any]:
    crit_ok = [f for f in CRITICAL_FIELDS if m.get(f) is not None]
    crit_miss = [f for f in CRITICAL_FIELDS if m.get(f) is None]
    imp_ok = [f for f in IMPORTANT_FIELDS if m.get(f) is not None]
    imp_miss = [f for f in IMPORTANT_FIELDS if m.get(f) is None]
    crit_pct = len(crit_ok) / len(CRITICAL_FIELDS) * 100
    imp_pct = len(imp_ok) / len(IMPORTANT_FIELDS) * 100
    # affidabile se almeno 5/7 critici
    reliable = len(crit_ok) >= 5
    return {
        "critical_ok": crit_ok,
        "critical_missing": crit_miss,
        "important_ok": imp_ok,
        "important_missing": imp_miss,
        "critical_pct": crit_pct,
        "important_pct": imp_pct,
        "reliable": reliable,
        "score_penalty": 0 if reliable else max(0, (5 - len(crit_ok)) * 5),
    }


def clamp(score: float, lo: float = 0, hi: float | None = None) -> float:
    if hi is None:
        return max(lo, score)
    return max(lo, min(hi, score))


@dataclass
class CategoryScore:
    name: str
    max_points: int
    points: float
    notes: list[str] = field(default_factory=list)


def _cat(name: str, max_p: int, pts: float, notes: list[str]) -> CategoryScore:
    return CategoryScore(name, max_p, clamp(pts, 0, max_p), notes)


def score_profitability(m: dict, sector: str) -> CategoryScore:
    notes: list[str] = []
    pts = 0.0

    if sector == "REIT":
        ffo = m.get("ffo")
        if ffo is None:
            # fallback EPS solo se FFO assente (con nota)
            if m.get("eps") is not None and m["eps"] > 0:
                return _cat("Profitabilità", 15, 6, ["FFO mancante — fallback EPS debole"])
            return _cat("Profitabilità", 15, 0, ["FFO mancante (metriche REIT)"])
        pts = 12 if ffo > 0 else 0
        notes.append(f"FFO={ffo}")
        if m.get("affo") is not None and m["affo"] > ffo:
            pts += 2
            notes.append("AFFO > FFO")
        if m.get("ss_noi") is not None:
            pts += 2 if m["ss_noi"] > 2 else (-2 if m["ss_noi"] < 0 else 0)
            notes.append(f"SS NOI={m['ss_noi']}%")
        return _cat("Profitabilità", 15, pts, notes)

    if sector == "BDC":
        nii = m.get("nii")
        if nii is None:
            if m.get("eps") is not None and m["eps"] > 0:
                return _cat("Profitabilità", 15, 5, ["NII mancante — fallback EPS"])
            return _cat("Profitabilità", 15, 0, ["NII mancante (metriche BDC)"])
        pts = 12 if nii > 0 else 0
        notes.append(f"NII={nii}")
        cov = m.get("nii_coverage")
        if cov is not None:
            pts += 3 if cov > 1.2 else (-5 if cov < 1.0 else 0)
            notes.append(f"NII coverage={cov}")
        return _cat("Profitabilità", 15, pts, notes)

    if sector == "FINANCIALS":
        eps = m.get("eps")
        if eps is None:
            return _cat("Profitabilità", 15, 0, ["EPS mancante"])
        pts = 10 if eps > 0 else 0
        notes.append(f"EPS={eps}")
        if m.get("roe") is not None:
            pts += 3 if m["roe"] > 12 else (1 if m["roe"] >= 8 else -3)
            notes.append(f"ROE={m['roe']}%")
        if m.get("roa") is not None:
            pts += 2 if m["roa"] > 1 else (-2 if m["roa"] < 0.5 else 0)
            notes.append(f"ROA={m['roa']}%")
        if m.get("nim") is not None:
            pts += 2 if m["nim"] > 2.5 else (-2 if m["nim"] < 1.5 else 0)
            notes.append(f"NIM={m['nim']}%")
        return _cat("Profitabilità", 15, pts, notes)

    if sector == "TECH":
        eps, eg = m.get("eps"), m.get("eps_growth")
        rg, gm = m.get("rev_growth"), m.get("gross_m")
        if eps is not None and eps < 0:
            if rg and rg > 30 and gm and gm > 60:
                pts = 10
                notes.append("EPS<0 ma growth+margin TECH OK")
            else:
                pts = 0
                notes.append("EPS negativo senza path chiaro")
            if m.get("forward_eps") and m["forward_eps"] > 0:
                pts = min(15, pts + 5)
                notes.append("Forward EPS > 0")
            return _cat("Profitabilità", 15, pts, notes)
        # path EPS positivo / standard sotto

    if sector == "HEALTHCARE":
        gm = m.get("gross_m")
        eps = m.get("eps")
        if gm is not None:
            pts += 8 if gm > 70 else 5 if gm >= 50 else 2
            notes.append(f"Gross (brevetti)={gm}%")
        if eps is not None and eps > 0:
            pts += 5
            notes.append("EPS>0")
        elif eps is not None and eps < 0:
            rg = m.get("rev_growth")
            pts += 3 if rg and rg > 20 else 0
            notes.append("EPS<0 (pipeline/biotech?)")
        if m.get("rd_rev") is not None:
            # R&D alto tipico; troppo alto senza growth = rischio
            rd = m["rd_rev"]
            pts += 2 if 10 <= rd <= 30 else (-2 if rd > 50 else 0)
            notes.append(f"R&D/Rev={rd}%")
        if pts == 0:
            return _cat("Profitabilità", 15, 0, ["Gross/EPS healthcare mancanti"])
        return _cat("Profitabilità", 15, pts, notes)

    # Default: EPS
    eps, eg = m.get("eps"), m.get("eps_growth")
    if eps is None:
        return _cat("Profitabilità", 15, 0, ["EPS mancante — 0 punti (non neutro)"])
    if eps <= 0:
        pts, notes = 0, ["EPS ≤ 0"]
    elif eg is not None and eg > 10:
        pts, notes = 15, [f"EPS>0 growth {eg:.1f}%"]
    elif eg is not None and eg >= 0:
        pts, notes = 12, [f"EPS>0 stable {eg:.1f}%"]
    elif eg is not None:
        pts, notes = 6, [f"EPS>0 decline {eg:.1f}%"]
    else:
        pts, notes = 10, ["EPS>0 (growth non trovato)"]
    fe = m.get("forward_eps")
    if fe is not None and eps:
        if fe > eps:
            pts += 3
            notes.append("Forward EPS > TTM")
        elif fe < eps:
            pts -= 3
            notes.append("Forward EPS < TTM")
    return _cat("Profitabilità", 15, pts, notes)


def score_valuation(m: dict, sector: str) -> CategoryScore:
    notes: list[str] = []
    pts = 0.0

    if sector == "REIT":
        # Prefer P/FFO se abbiamo ffo+price, altrimenti P/B / NAV
        price, ffo, nav = m.get("price"), m.get("ffo"), m.get("nav")
        if price and ffo and ffo > 0:
            pffo = price / ffo
            pts = 15 if pffo < 12 else 12 if pffo < 16 else 8 if pffo < 20 else 0
            notes.append(f"P/FFO={pffo:.1f}")
        elif m.get("nav_premium") is not None:
            np_ = m["nav_premium"]
            pts = 15 if np_ < -10 else 10 if np_ <= 5 else 5 if np_ <= 20 else 0
            notes.append(f"NAV premium={np_:.1f}%")
        elif m.get("pb") is not None:
            pts = 12 if m["pb"] < 1 else 8 if m["pb"] < 1.5 else 3
            notes.append(f"P/B={m['pb']} (proxy NAV)")
        else:
            return _cat("Valutazione", 15, 0, ["P/FFO e NAV mancanti"])
        return _cat("Valutazione", 15, pts, notes)

    if sector == "BDC":
        if m.get("nav_premium") is not None:
            np_ = m["nav_premium"]
            pts = 15 if np_ < -5 else 10 if np_ <= 0 else 5 if np_ <= 10 else 0
            notes.append(f"NAV premium={np_:.1f}%")
            return _cat("Valutazione", 15, pts, notes)
        pb = m.get("pb")
        if pb is None:
            return _cat("Valutazione", 15, 0, ["P/NAV (P/B) mancante"])
        pts = 15 if pb < 0.9 else 10 if pb <= 1.0 else 5 if pb <= 1.2 else 0
        notes.append(f"P/B≈P/NAV={pb}")
        return _cat("Valutazione", 15, pts, notes)

    if sector == "FINANCIALS":
        pe = m.get("pe")
        if pe is None or pe <= 0:
            return _cat("Valutazione", 15, 0, ["P/E mancante"])
        pts = 15 if pe < 10 else 12 if pe < 12 else 8 if pe < 15 else 0
        notes.append(f"P/E={pe}")
        pb = m.get("pb")
        if pb is not None:
            pts += 5 if pb < 1 else 3 if pb <= 1.5 else (-3 if pb > 2 else 0)
            notes.append(f"P/B={pb}")
        return _cat("Valutazione", 15, pts, notes)

    if sector == "ENERGY":
        ev = m.get("ev_ebitda")
        if ev is None:
            pe = m.get("pe")
            if pe and pe > 0:
                return _cat("Valutazione", 15, 6, [f"EV/EBITDA mancante — fallback P/E={pe}"])
            return _cat("Valutazione", 15, 0, ["EV/EBITDA mancante (chiave Energy)"])
        pts = 15 if ev < 6 else 12 if ev < 8 else 8 if ev < 12 else 4 if ev < 15 else 0
        notes.append(f"EV/EBITDA={ev}")
        return _cat("Valutazione", 15, pts, notes)

    if sector == "TECH" and (m.get("eps") is None or (m.get("eps") is not None and m["eps"] < 0)):
        ps = m.get("ps")
        if ps is None:
            return _cat("Valutazione", 15, 0, ["P/S mancante"])
        pts = 15 if ps < 10 else 10 if ps < 20 else 5 if ps < 30 else 0
        notes.append(f"P/S={ps}")
        if m.get("peg") and m["peg"] < 1.5:
            pts += 5
            notes.append(f"PEG={m['peg']}")
        return _cat("Valutazione", 15, pts, notes)

    if sector == "COMMUNICATION":
        ev = m.get("ev_ebitda")
        if ev is not None:
            pts = 12 if ev < 8 else 8 if ev < 12 else 4 if ev < 18 else 0
            notes.append(f"EV/EBITDA={ev}")
        pe = m.get("pe")
        if pe and pe > 0:
            pts += 3 if pe < 15 else 0
            notes.append(f"P/E={pe}")
        if pts == 0:
            return _cat("Valutazione", 15, 0, ["EV/EBITDA e P/E mancanti"])
        return _cat("Valutazione", 15, pts, notes)

    pe = m.get("pe")
    if pe is None or pe <= 0:
        if m.get("ps"):
            ps = m["ps"]
            pts = 8 if ps < 5 else 4 if ps < 10 else 0
            return _cat("Valutazione", 15, pts, [f"P/E mancante, fallback P/S={ps}"])
        if m.get("ev_ebitda"):
            ev = m["ev_ebitda"]
            pts = 10 if ev < 10 else 5 if ev < 15 else 0
            return _cat("Valutazione", 15, pts, [f"P/E mancante, EV/EBITDA={ev}"])
        return _cat("Valutazione", 15, 0, ["P/E mancante"])
    pts = 15 if pe < 12 else 12 if pe < 18 else 8 if pe < 25 else 4 if pe < 40 else 0
    notes.append(f"P/E={pe}")
    if m.get("peg") is not None:
        pts += 5 if m["peg"] < 1 else (-3 if m["peg"] > 2 else 0)
        notes.append(f"PEG={m['peg']}")
    if m.get("pb") is not None:
        pts += 5 if m["pb"] < 1 else (-3 if m["pb"] > 3 else 0)
        notes.append(f"P/B={m['pb']}")
    if m.get("ev_ebitda") is not None:
        pts += 3 if m["ev_ebitda"] < 10 else (-3 if m["ev_ebitda"] > 20 else 0)
    return _cat("Valutazione", 15, pts, notes)


def score_health(m: dict, sector: str) -> CategoryScore:
    notes: list[str] = []
    pts = 0.0

    if sector == "FINANCIALS":
        if m.get("cet1") is None:
            # senza CET1 usa NPL / leverage soft
            if m.get("npl") is not None:
                npl = m["npl"]
                pts = 10 if npl < 2 else 6 if npl < 5 else 0
                notes.append(f"CET1 mancante; NPL={npl}%")
                return _cat("Salute Finanziaria", 15, pts, notes)
            return _cat("Salute Finanziaria", 15, 0, ["CET1 mancante (carica TIKR/report banca)"])
        c = m["cet1"]
        pts = 15 if c > 12 else 12 if c >= 10 else 6 if c >= 8 else 0
        notes.append(f"CET1={c}%")
        if m.get("npl") is not None:
            pts += 3 if m["npl"] < 2 else (-5 if m["npl"] > 5 else 0)
            notes.append(f"NPL={m['npl']}%")
        return _cat("Salute Finanziaria", 15, pts, notes)

    if sector in ("REIT", "ENERGY"):
        d = m.get("debt_ebitda")
        if d is None:
            # fallback D/E
            de = m.get("de")
            if de is not None:
                pts = 8 if de < 1 else 4 if de < 2 else 0
                return _cat("Salute Finanziaria", 15, pts, [f"Debt/EBITDA mancante; D/E={de:.2f}"])
            return _cat("Salute Finanziaria", 15, 0, ["Debt/EBITDA mancante"])
        thr = (5, 7, 10) if sector == "REIT" else (2.5, 3.5, 5)
        pts = 15 if d < thr[0] else 12 if d < thr[1] else 6 if d < thr[2] else 0
        notes.append(f"Debt/EBITDA={d}")
        if m.get("interest_cov") is not None:
            pts += 3 if m["interest_cov"] > 3 else (-3 if m["interest_cov"] < 1.5 else 0)
            notes.append(f"Interest cov={m['interest_cov']}")
        return _cat("Salute Finanziaria", 15, pts, notes)

    if sector == "BDC":
        de = m.get("de")
        if de is None:
            return _cat("Salute Finanziaria", 15, 0, ["D/E mancante (limite BDC ~2:1)"])
        pts = 15 if de < 1.0 else 10 if de < 1.25 else 5 if de <= 1.5 else 0
        notes.append(f"D/E={de:.2f} (reg. max ~2)")
        if m.get("non_accrual") is not None:
            pts += 3 if m["non_accrual"] < 1.5 else (-5 if m["non_accrual"] > 4 else 0)
            notes.append(f"Non-accrual={m['non_accrual']}%")
        return _cat("Salute Finanziaria", 15, pts, notes)

    if sector == "INDUSTRIAL":
        de = m.get("de")
        if de is None:
            return _cat("Salute Finanziaria", 15, 0, ["D/E mancante"])
        pts = 12 if de < 0.5 else 8 if de < 1 else 3 if de <= 1.5 else 0
        notes.append(f"D/E={de:.2f}")
        if m.get("interest_cov") is not None:
            pts += 3 if m["interest_cov"] > 5 else (-3 if m["interest_cov"] < 2 else 0)
        return _cat("Salute Finanziaria", 15, pts, notes)

    de = m.get("de")
    if de is None:
        return _cat("Salute Finanziaria", 15, 0, ["D/E mancante — 0 punti"])
    pts = 15 if de < 0.3 else 12 if de < 0.6 else 6 if de <= 1 else 0
    notes.append(f"D/E={de:.2f}")
    cr = m.get("current_ratio")
    if cr is not None:
        pts += 5 if cr > 2 else 2 if cr >= 1 else -5
        notes.append(f"Current={cr}")
    if m.get("interest_cov") is not None:
        pts += 3 if m["interest_cov"] > 5 else (-3 if m["interest_cov"] < 2 else 0)
    if m.get("altman") is not None:
        pts += 2 if m["altman"] > 3 else (-5 if m["altman"] < 1.8 else 0)
    return _cat("Salute Finanziaria", 15, pts, notes)


def score_cashflow(m: dict, sector: str) -> CategoryScore:
    notes: list[str] = []
    pts = 0.0

    if sector == "REIT":
        if m.get("ffo") and m["ffo"] > 0:
            pts += 5
            notes.append("FFO > 0")
        if m.get("affo") and m["affo"] > 0:
            pts += 3
            notes.append("AFFO > 0")
        if pts == 0:
            # fallback FCF
            if m.get("fcf") and m["fcf"] > 0:
                return _cat("Qualità Cash Flow", 10, 4, ["FFO/AFFO mancanti — fallback FCF>0"])
            return _cat("Qualità Cash Flow", 10, 0, ["FFO/AFFO mancanti"])
        return _cat("Qualità Cash Flow", 10, pts, notes)

    if sector == "BDC":
        if m.get("nii") and m["nii"] > 0:
            pts = 5
            notes.append("NII > 0")
            if m.get("nii_coverage") is not None:
                pts += 5 if m["nii_coverage"] >= 1.1 else (-3 if m["nii_coverage"] < 1 else 2)
                notes.append(f"Coverage={m['nii_coverage']}")
            return _cat("Qualità Cash Flow", 10, pts, notes)
        return _cat("Qualità Cash Flow", 10, 0, ["NII mancante"])

    if sector == "ENERGY":
        fcf = m.get("fcf")
        if fcf is None:
            return _cat("Qualità Cash Flow", 10, 0, ["FCF mancante"])
        pts = 5 if fcf > 0 else 0
        notes.append("FCF>0" if fcf > 0 else "FCF≤0")
        if m.get("fcf_yield") is not None:
            pts += 5 if m["fcf_yield"] > 6 else 2 if m["fcf_yield"] > 3 else 0
            notes.append(f"FCF Yield={m['fcf_yield']:.1f}%")
        return _cat("Qualità Cash Flow", 10, pts, notes)

    if sector == "COMMUNICATION":
        # FCF post-capex: usiamo FCF yield
        fy = m.get("fcf_yield")
        fcf = m.get("fcf")
        if fcf is None and fy is None:
            return _cat("Qualità Cash Flow", 10, 0, ["FCF mancante"])
        pts = 5 if fcf and fcf > 0 else 0
        if fy is not None:
            pts += 5 if fy > 5 else 2 if fy > 2 else 0
            notes.append(f"FCF Yield post-capex≈{fy:.1f}%")
        if m.get("capex_rev") is not None:
            notes.append(f"Capex/Rev={m['capex_rev']}%")
        return _cat("Qualità Cash Flow", 10, pts, notes)

    fcf = m.get("fcf")
    if fcf is None:
        return _cat("Qualità Cash Flow", 10, 0, ["FCF mancante — 0 punti"])
    if fcf > 0:
        pts += 5
        notes.append("FCF > 0")
    else:
        pts -= 5
        notes.append("FCF ≤ 0")
    if m.get("fcf_ni") is not None and m["fcf_ni"] > 0.8:
        pts += 3
        notes.append("FCF conversion alta")
    if m.get("fcf_yield") is not None:
        pts += 2 if m["fcf_yield"] > 5 else (-5 if m["fcf_yield"] < 0 else 0)
        notes.append(f"FCF Yield={m['fcf_yield']:.1f}%")
    ocf, ni = m.get("ocf"), m.get("net_income")
    if ocf is not None and ni is not None and ocf > ni:
        pts += 2
    if ocf is not None and ocf < 0:
        pts -= 5
    return _cat("Qualità Cash Flow", 10, pts, notes)


def score_dividend(m: dict, sector: str) -> CategoryScore:
    y, p = m.get("div_yield"), m.get("payout")
    notes: list[str] = []

    if y is None:
        # settori growth: assenza dividendo OK
        if sector in ("TECH", "HEALTHCARE"):
            return _cat("Dividendo", 10, 8, ["Niente yield → tipico growth"])
        if sector in ("INDUSTRIAL", "CONSUMER", "GENERICO"):
            return _cat("Dividendo", 10, 5, ["Yield non trovato → neutro"])
        return _cat("Dividendo", 10, 3, ["Yield mancante (settore income-oriented)"])

    notes.append(f"Yield={y}%")
    if sector == "TECH":
        pts = 10 if 0.5 <= y <= 2 else (3 if y > 3 else 8)
    elif sector == "BDC":
        pts = 10 if 8 <= y <= 12 else (0 if y > 15 else 3 if y < 7 else 6)
        if m.get("nii_coverage") is not None and m["nii_coverage"] < 1:
            pts = min(pts, 2)
            notes.append("Coverage < 1 — dividendo a rischio")
    elif sector == "REIT":
        pts = 10 if 4 <= y <= 8 and (p is None or p < 90) else (0 if y > 10 else 6)
    elif sector == "ENERGY":
        pts = 10 if 3 <= y <= 7 and (p is None or p < 80) else (0 if y > 10 or (p and p > 100) else 5)
    elif sector == "FINANCIALS":
        pts = 10 if 2 <= y <= 5 and (p is None or p < 60) else (3 if y > 7 else 6)
    elif sector == "COMMUNICATION":
        pts = 10 if 3 <= y <= 7 else (0 if y > 10 else 5)
    else:
        if p and p > 100:
            pts = 0
        elif y > 8:
            pts = 0
        elif 2 <= y <= 5 and (p is None or p < 60):
            pts = 10
        elif 2 <= y <= 5:
            pts = 7
        elif y < 2:
            pts = 3
        else:
            pts = 4
    if p is not None:
        notes.append(f"Payout={p}%")
    return _cat("Dividendo", 10, pts, notes)


def score_growth(m: dict, sector: str) -> CategoryScore:
    rg = m.get("rev_growth")
    notes: list[str] = []
    pts = 0.0

    if sector == "REIT":
        ss = m.get("ss_noi")
        if ss is not None:
            pts = 10 if ss > 4 else 7 if ss >= 2 else 4 if ss >= 0 else 0
            notes.append(f"SS NOI={ss}%")
            return _cat("Crescita", 10, pts, notes)
        if rg is None:
            return _cat("Crescita", 10, 0, ["SS NOI / revenue growth mancanti"])
        pts = 7 if rg > 5 else 4 if rg >= 0 else 0
        notes.append(f"Rev YoY={rg}% (proxy)")
        return _cat("Crescita", 10, pts, notes)

    if sector == "CONSUMER":
        ss = m.get("ss_sales")
        if ss is not None:
            pts = 10 if ss > 3 else 7 if ss >= 1 else 4 if ss >= 0 else 0
            notes.append(f"Same-store sales={ss}%")
            if rg is not None:
                notes.append(f"Rev YoY={rg}%")
            return _cat("Crescita", 10, pts, notes)

    if sector == "COMMUNICATION":
        # subscriber / ARPU proxies via rev growth
        if rg is None:
            return _cat("Crescita", 10, 0, ["Revenue/subscriber growth mancante"])
        pts = 10 if rg > 8 else 7 if rg >= 3 else 4 if rg >= 0 else 0
        notes.append(f"Rev YoY={rg}%")
        if m.get("churn") is not None:
            pts += 2 if m["churn"] < 1.5 else (-3 if m["churn"] > 3 else 0)
            notes.append(f"Churn={m['churn']}%")
        return _cat("Crescita", 10, pts, notes)

    if rg is None:
        return _cat("Crescita", 10, 0, ["Revenue growth mancante — 0 punti"])
    notes.append(f"Rev YoY={rg}%")
    if sector == "TECH":
        pts = 10 if rg > 30 else 8 if rg >= 20 else 5 if rg >= 10 else 0
        if m.get("rule_of_40") is not None:
            r40 = m["rule_of_40"]
            pts += 3 if r40 >= 40 else (-2 if r40 < 20 else 0)
            notes.append(f"Rule of 40={r40:.0f}")
        if m.get("nrr") is not None:
            pts += 2 if m["nrr"] >= 110 else 0
            notes.append(f"NRR={m['nrr']}%")
    elif sector == "HEALTHCARE":
        pts = 10 if rg > 15 else 7 if rg >= 8 else 4 if rg >= 0 else 0
    elif sector == "INDUSTRIAL":
        pts = 10 if rg > 10 else 7 if rg >= 3 else 4 if rg >= 0 else 0
        if m.get("book_to_bill") is not None:
            pts += 2 if m["book_to_bill"] > 1.0 else (-2 if m["book_to_bill"] < 0.9 else 0)
            notes.append(f"Book-to-bill={m['book_to_bill']}")
    else:
        pts = 10 if rg > 15 else 7 if rg >= 5 else 4 if rg >= 0 else 0

    if m.get("eps_growth") and m["eps_growth"] > 20:
        pts += 3
        notes.append(f"EPS growth={m['eps_growth']}%")
    if m.get("rev_cagr_3y") is not None:
        pts += 2 if m["rev_cagr_3y"] > 10 else (-3 if m["rev_cagr_3y"] < 0 else 0)
    return _cat("Crescita", 10, pts, notes)


def score_margins(m: dict, sector: str) -> CategoryScore:
    gm, om, nm = m.get("gross_m"), m.get("op_m"), m.get("net_m")
    notes, pts = [], 0.0

    if sector == "FINANCIALS":
        # cost/income + ROE già in part; qui efficienza
        if m.get("cost_income") is not None:
            ci = m["cost_income"]
            pts += 5 if ci < 55 else 3 if ci < 65 else 0
            notes.append(f"Cost/Income={ci}%")
        if m.get("nim") is not None:
            pts += 3 if m["nim"] > 2.5 else 0
            notes.append(f"NIM={m['nim']}%")
        if m.get("roe") is not None:
            pts += 3 if m["roe"] > 12 else 0
        if pts == 0:
            return _cat("Efficienza/Margini", 8, 0, ["Cost/Income o NIM mancanti — carica TIKR"])
        return _cat("Efficienza/Margini", 8, pts, notes)

    if sector == "TECH":
        if gm is not None:
            pts += 3 if gm > 70 else 2 if gm >= 50 else 0
            notes.append(f"Gross={gm}%")
        if om is not None:
            pts += 2 if om > 20 else 1 if om >= 10 else 0
            notes.append(f"Op={om}%")
        if m.get("fcf_margin") is not None:
            pts += 3 if m["fcf_margin"] > 20 else 1 if m["fcf_margin"] > 10 else 0
            notes.append(f"FCF margin={m['fcf_margin']:.1f}%")
        if pts == 0:
            return _cat("Efficienza/Margini", 8, 0, ["Margini TECH mancanti"])
        return _cat("Efficienza/Margini", 8, pts, notes)

    if sector in ("ENERGY", "COMMUNICATION", "INDUSTRIAL"):
        em = m.get("ebitda_m") or om
        if em is not None:
            thr = (35, 25) if sector == "COMMUNICATION" else (25, 15)
            pts += 4 if em > thr[0] else 2 if em >= thr[1] else 0
            notes.append(f"EBITDA/Op margin={em}%")
        if m.get("roic") is not None and sector == "INDUSTRIAL":
            pts += 3 if m["roic"] > 12 else (-2 if m["roic"] < 5 else 0)
            notes.append(f"ROIC={m['roic']}%")
        if m.get("capex_rev") is not None and sector == "COMMUNICATION":
            # network needs capex; troppo alto erode FCF
            pts += 1 if m["capex_rev"] < 20 else (-2 if m["capex_rev"] > 35 else 0)
            notes.append(f"Capex/Rev={m['capex_rev']}%")
        if pts == 0 and gm is None and om is None:
            return _cat("Efficienza/Margini", 8, 0, ["Margini mancanti"])
        if gm is not None and pts < 4:
            pts += 2 if gm > 30 else 0
        return _cat("Efficienza/Margini", 8, pts, notes)

    if sector == "HEALTHCARE":
        if gm is not None:
            pts += 4 if gm > 70 else 2 if gm >= 50 else 0
            notes.append(f"Gross={gm}%")
        if m.get("rd_rev") is not None:
            notes.append(f"R&D/Rev={m['rd_rev']}%")
        if om is not None:
            pts += 2 if om > 15 else 0
        if pts == 0:
            return _cat("Efficienza/Margini", 8, 0, ["Gross margin healthcare mancante"])
        return _cat("Efficienza/Margini", 8, pts, notes)

    if sector == "CONSUMER":
        if gm is not None:
            pts += 3 if gm > 35 else 2 if gm >= 25 else 0
            notes.append(f"Gross={gm}%")
        if om is not None:
            pts += 3 if om > 10 else 1 if om >= 5 else 0
            notes.append(f"Op={om}%")
        if m.get("inventory_turns") is not None:
            pts += 2 if m["inventory_turns"] > 5 else 0
            notes.append(f"Inv turns={m['inventory_turns']}")
        if pts == 0:
            return _cat("Efficienza/Margini", 8, 0, ["Margini consumer mancanti"])
        return _cat("Efficienza/Margini", 8, pts, notes)

    if gm is None and om is None and nm is None and m.get("roe") is None:
        return _cat("Efficienza/Margini", 8, 0, ["Margini mancanti"])
    if gm is not None:
        pts += 3 if gm > 40 else 2 if gm >= 20 else 0
        notes.append(f"Gross={gm}%")
    if om is not None:
        pts += 3 if om > 15 else 2 if om >= 5 else (-2 if om < 0 else 0)
        notes.append(f"Op={om}%")
    if nm is not None:
        pts += 2 if nm > 10 else (-2 if nm < 0 else 0)
    if m.get("roe") is not None:
        pts += 3 if m["roe"] > 15 else (-3 if m["roe"] < 5 else 0)
        notes.append(f"ROE={m['roe']}%")
    if m.get("roa") is not None and m["roa"] > 5:
        pts += 2
    return _cat("Efficienza/Margini", 8, pts, notes)


def score_technical(m: dict) -> CategoryScore:
    notes, pts = [], 0.0
    price, s50, s200 = m.get("price"), m.get("sma50"), m.get("sma200")
    found = False
    if price is not None and s200 is not None:
        found = True
        if price > s200:
            pts += 3
            notes.append("> SMA200")
    if price is not None and s50 is not None:
        found = True
        if price > s50:
            pts += 2
            notes.append("> SMA50")
    if s50 is not None and s200 is not None and s50 > s200:
        pts += 2
        notes.append("Golden cross")
    if m.get("rsi") is not None:
        found = True
        r = m["rsi"]
        pts += 1 if 40 <= r <= 60 or r < 30 else (-2 if r > 70 else 0)
        notes.append(f"RSI={r}")
    if m.get("week52") is not None:
        found = True
        w = m["week52"]
        pts += 2 if w > 0 else (-2 if w < -40 else 0)
    if m.get("avg_vol") and m["avg_vol"] > 1e6:
        pts += 1
    if not found:
        return _cat("Tecnico/Momentum", 8, 0, ["Dati tecnici insufficienti"])
    return _cat("Tecnico/Momentum", 8, pts, notes)


def score_analysts(m: dict) -> CategoryScore:
    notes: list[str] = []
    n = m.get("n_analysts")
    sb = m.get("strong_buy") or 0
    b = m.get("buy") or 0
    h = m.get("hold") or 0
    s = m.get("sell") or 0
    ss = m.get("strong_sell") or 0
    total = int(sb + b + h + s + ss) or (int(n) if n else 0)

    if total < 1 or total > 80:
        price, target = m.get("price"), m.get("target")
        if price and target and price > 0:
            up = (target / price - 1) * 100
            pts = 5 if up > 25 else 4 if up >= 10 else (1 if target < price else 3)
            return _cat("Consenso Analisti", 10, min(5, pts), [f"Pochi/niente rating; target upside {up:.1f}%", "Affidabilità bassa"])
        return _cat("Consenso Analisti", 10, 0, ["Consensus analisti non trovato"])

    buy_pct = (sb + b) / total * 100
    sell_pct = (s + ss) / total * 100
    pts = 8 if buy_pct > 70 else 6 if buy_pct >= 50 else 3 if buy_pct >= 30 else 0
    notes.append(f"Buy+SB={buy_pct:.0f}% su {total} analisti")
    if sell_pct > 25:
        pts -= 3
        notes.append(f"Sell={sell_pct:.0f}%")
    price, target = m.get("price"), m.get("target")
    if price and target and price > 0:
        up = (target / price - 1) * 100
        pts += 2 if up > 25 else 1 if up >= 10 else (-2 if target < price else 0)
        notes.append(f"Target ${target:.2f} ({up:+.1f}%)")
    if total < 5:
        pts = min(pts, 5)
        notes.append("Affidabilità bassa (<5 analisti)")
    return _cat("Consenso Analisti", 10, pts, notes)


def score_ownership(m: dict) -> CategoryScore:
    notes, pts = [], 0.0
    found = False
    if m.get("inst") is not None:
        found = True
        pts += 2 if m["inst"] > 60 else (-2 if m["inst"] < 20 else 0)
        notes.append(f"Institutional={m['inst']}%")
    if m.get("short_pct") is not None:
        found = True
        pts += 1 if m["short_pct"] < 5 else (-3 if m["short_pct"] > 20 else 0)
        notes.append(f"Short%={m['short_pct']}")
    if m.get("short_ratio") is not None:
        found = True
        pts += 1 if m["short_ratio"] < 3 else (-2 if m["short_ratio"] > 10 else 0)
    if not found:
        return _cat("Insider/Institutional", 6, 0, ["Ownership/short non trovati"])
    return _cat("Insider/Institutional", 6, pts, notes)


def score_context(m: dict, sector: str) -> CategoryScore:
    from sectors import SECTOR_LABELS

    notes, pts = [f"Settore {SECTOR_LABELS.get(sector, sector)}"], 1.0
    # bias leggeri per settori growth vs ciclici
    if sector == "TECH":
        pts += 2
    elif sector in ("HEALTHCARE", "CONSUMER"):
        pts += 1
    elif sector in ("ENERGY", "INDUSTRIAL"):
        pts += 0  # ciclici: nessun bonus
    mcap = m.get("market_cap")
    if mcap is not None:
        pts += 2 if mcap > 10e9 else 1 if mcap >= 2e9 else (-2 if mcap < 500e6 else 0)
        notes.append(f"Mkt Cap={mcap/1e9:.2f}B" if mcap >= 1e9 else f"Mkt Cap={mcap/1e6:.0f}M")
    if m.get("beta") is not None:
        # utilities/energy preferiscono beta basso
        if sector == "ENERGY":
            pts += 2 if m["beta"] < 0.9 else (-1 if m["beta"] > 1.5 else 0)
        else:
            pts += 2 if m["beta"] < 1 else (-2 if m["beta"] > 2 else 0)
        notes.append(f"Beta={m['beta']}")
    return _cat("Settore/Contesto", 6, pts, notes)


def risk_profile(total: float, m: dict, red_flags: int, reliable: bool) -> tuple[int, str]:
    if not reliable:
        return 5, "Aggressivo"
    risk = 3
    if m.get("market_cap") and m["market_cap"] > 50e9 and (m.get("beta") or 1) < 1.2:
        risk = 2
    if m.get("market_cap") and m["market_cap"] < 500e6:
        risk = 4
    if red_flags >= 3:
        risk = 5
    if total >= 80 and risk > 2:
        risk = max(1, risk - 1)
    if total < 40:
        risk = min(5, risk + 1)
    profilo = "Conservativo" if risk <= 2 else "Moderato" if risk == 3 else "Aggressivo"
    return risk, profilo


def verdict_from_score(total: float, reliable: bool) -> str:
    if not reliable:
        return "DATI INSUFFICIENTI"
    if total >= 80:
        return "COMPRA FORTE"
    if total >= 60:
        return "COMPRA"
    if total >= 40:
        return "NEUTRO"
    if total >= 20:
        return "EVITA"
    return "EVITA FORTE"


def buy_target(m: dict, sector: str, total: float, reliable: bool) -> str:
    if not reliable:
        return "NESSUN PREZZO — verifica ticker Yahoo + HTML Investing/TIKR"
    price = m.get("price")
    if price is None:
        return "N/D — prezzo non estratto"
    if total < 20:
        return "NESSUN PREZZO — EVITA"
    if total >= 80:
        a = price * 0.95
    elif total >= 60:
        a = price * 0.90
    elif total >= 40:
        a = price * 0.85
    else:
        a = price * 0.75
    cands = [("fondamentale", a)]
    n = m.get("n_analysts") or 0
    if n >= 5 and m.get("target"):
        cands.append(("target×0.92", m["target"] * 0.92))
    if sector in ("REIT", "BDC") and m.get("nav"):
        mult = 1.10 if sector == "REIT" else 1.05
        cands.append(("NAV cap", m["nav"] * mult))
    elif sector == "FINANCIALS" and m.get("pb") and m["pb"] > 1.5 and m.get("bvps"):
        cands.append(("BVPS cap", m["bvps"] * 1.15))
    elif m.get("pb") and m["pb"] > 1.5 and m.get("bvps"):
        cands.append(("BVPS cap", m["bvps"] * 1.20))
    best_name, best_val = min(cands, key=lambda x: x[1])
    discount = (1 - best_val / price) * 100
    detail = ", ".join(f"{n}=${v:.2f}" for n, v in cands)
    return f"${best_val:.2f} (sconto {discount:.1f}% | min di: {detail})"


def collect_red_flags(m: dict, sector: str) -> list[str]:
    flags: list[str] = []
    pe, rg, de = m.get("pe"), m.get("rev_growth"), m.get("de")
    if pe is not None and pe <= 0 and rg is not None and rg < 0 and de is not None and de > 1:
        flags.append("P/E neg + revenue decline + D/E>1")
    y, p, fcf = m.get("div_yield"), m.get("payout"), m.get("fcf")
    if y and y > 15 and p and p > 100 and fcf is not None and fcf < 0:
        flags.append("Yield>15% + payout>100% + FCF neg")
    z, ic, cr = m.get("altman"), m.get("interest_cov"), m.get("current_ratio")
    if z is not None and z < 1.8 and ic is not None and ic < 1 and cr is not None and cr < 1:
        flags.append("Z-Score + coverage + current critici")
    if sector == "TECH" and rg is not None and rg < 10 and fcf is not None and fcf < 0:
        flags.append("[TECH] Growth bassa + FCF negativo")
    if sector == "FINANCIALS":
        if m.get("cet1") is not None and m["cet1"] < 8:
            flags.append("[FINANCIALS] CET1 < 8%")
        if m.get("npl") is not None and m["npl"] > 5:
            flags.append("[FINANCIALS] NPL > 5%")
    if sector == "REIT":
        if m.get("debt_ebitda") is not None and m["debt_ebitda"] > 10:
            flags.append("[REIT] Debt/EBITDA > 10")
        if p and p > 100:
            flags.append("[REIT] Payout > 100%")
    if sector == "BDC":
        if m.get("nii_coverage") is not None and m["nii_coverage"] < 1.0:
            flags.append("[BDC] NII coverage < 1.0")
        if m.get("nav_premium") is not None and m["nav_premium"] < -20:
            flags.append("[BDC] NAV discount > 20%")
    if sector == "ENERGY" and m.get("debt_ebitda") is not None and m["debt_ebitda"] > 5:
        flags.append("[ENERGY] Debt/EBITDA elevato")
    return flags


def fmt_money(x: float | None) -> str:
    if x is None:
        return "N/D"
    ax, sign = abs(x), "-" if x < 0 else ""
    if ax >= 1e9:
        return f"{sign}${ax/1e9:.2f}B"
    if ax >= 1e6:
        return f"{sign}${ax/1e6:.1f}M"
    return f"{sign}${ax:,.2f}"


def fmt_num(x: float | None, suffix: str = "") -> str:
    if x is None:
        return "N/D"
    return f"{x:.2f}{suffix}"


PAGES_GUIDE = """
📄 COME MIGLIORARE LA COPERTURA DATI:

1) Controlla il ticker Yahoo (es. GOOGL, BRK-B, SAP.DE)
2) Investing.com — overview SingleFile (obbligatorio)
3) TIKR — tab mirate SingleFile:
   Overview | Financials (FFO/NII/FCF) | Ratios (CET1/Z-Score/NRR) |
   Valuation (P/FFO/NAV) | Estimates (growth/CAGR)
4) Opzionali: Finviz, MarketWatch, GuruFocus, TipRanks, Morningstar (SingleFile)

Yahoo (prezzo, P/E, EPS, D/E, FCF, target, analisti) arriva in automatico via API.
Se Yahoo non ha FCF → si usa TIKR Cash Flow (riga Free Cash Flow) oppure FCF = OCF − CapEx.
Metriche niche (FFO, CET1, SS NOI, NRR) spesso solo da TIKR/report.
"""


def run_analysis(
    investing: str,
    tikr: str,
    sector: str,
    yahoo_metrics: dict[str, Any] | None = None,
    extra_sources: dict[str, str] | None = None,
) -> dict[str, Any]:
    from sectors import SECTOR_KEY_METRICS, normalize_sector, sector_metrics_blurb
    from smart_money import score_smart_money, smart_money_to_dict

    sector = normalize_sector(sector)
    m = extract_metrics(
        investing,
        tikr,
        yahoo_metrics=yahoo_metrics,
        extra_sources=extra_sources,
    )
    cov = data_coverage(m)

    cats = [
        score_profitability(m, sector),
        score_valuation(m, sector),
        score_health(m, sector),
        score_cashflow(m, sector),
        score_dividend(m, sector),
        score_growth(m, sector),
        score_margins(m, sector),
        score_technical(m),
        score_analysts(m),
        score_ownership(m),
        score_context(m, sector),
    ]

    base_total = sum(c.points for c in cats)
    flags = collect_red_flags(m, sector)
    if len(flags) >= 3:
        base_total -= 10
    if not cov["reliable"]:
        base_total -= cov["score_penalty"]
    base_total = clamp(base_total, 0, 100)

    reliable = cov["reliable"]
    prelim_verdict = verdict_from_score(base_total, reliable)
    ticker = m.get("ticker") or "N/D"

    sm = score_smart_money(
        ticker,
        base_score=base_total,
        reliable=reliable,
        preliminary_verdict=prelim_verdict,
    )
    cats.append(
        _cat(
            "Smart Money 13F",
            3,
            max(0.0, sm.bonus),  # in categoria mostriamo solo il positivo; malus sul totale
            sm.notes[:5] or ["Nessun dato"],
        )
    )
    # Malus vendite applicato anche se categoria mostra 0
    total = clamp(base_total + sm.bonus, 0, 100)

    risk, profilo = risk_profile(total, m, len(flags), reliable)
    verdict = verdict_from_score(total, reliable)
    # Sicurezza: bonus non può salvare un EVITA → se prelim era EVITA*, resta EVITA*
    if prelim_verdict in {"EVITA", "EVITA FORTE"} and verdict not in {"EVITA", "EVITA FORTE", "DATI INSUFFICIENTI"}:
        verdict = prelim_verdict
        total = min(total, 39.0)
    target_txt = buy_target(m, sector, total, reliable)

    n = int(m.get("n_analysts") or 0)
    sb, b, h, s, ss = (m.get("strong_buy") or 0), (m.get("buy") or 0), (m.get("hold") or 0), (m.get("sell") or 0), (m.get("strong_sell") or 0)
    tot_a = int(sb + b + h + s + ss)
    if tot_a > 0:
        cons = f"{sb/tot_a*100:.0f}% StrongBuy | {b/tot_a*100:.0f}% Buy | {h/tot_a*100:.0f}% Hold | {s/tot_a*100:.0f}% Sell | {ss/tot_a*100:.0f}% StrongSell"
    else:
        cons = "N/D"

    price = m.get("price")
    up = (m["target"] / price - 1) * 100 if price and m.get("target") else None

    lines = []
    lines.append("═══════════════════════════════════════")
    lines.append(f"📊 AZIONE: {m.get('name')} ({ticker})")
    lines.append(f"🏷️ SETTORE: {sector}")
    lines.append(f"💰 PREZZO: {fmt_num(price)} | Market Cap: {fmt_money(m.get('market_cap'))}")
    lines.append(f"📈 VOTO: {total:.0f}/100 | Rischio: {risk}/5 | Profilo: {profilo}")
    if sm.bonus:
        lines.append(f"   (base {base_total:.0f} {sm.bonus:+.0f} smart money 13F)")
    lines.append("")
    lines.append(sector_metrics_blurb(sector))
    lines.append("")
    lines.append(
        f"📦 COPERTURA DATI: critici {len(cov['critical_ok'])}/{len(CRITICAL_FIELDS)} "
        f"({cov['critical_pct']:.0f}%) | importanti {len(cov['important_ok'])}/{len(IMPORTANT_FIELDS)} "
        f"({cov['important_pct']:.0f}%)"
    )
    lines.append(f"   ✅ Trovati: {', '.join(cov['critical_ok']) or '—'}")
    lines.append(f"   ❌ Mancanti: {', '.join(cov['critical_missing']) or '—'}")
    if extra_sources:
        loaded = ", ".join(sorted(extra_sources.keys()))
        lines.append(f"   📎 Fonti HTML extra: {loaded}")
    if not reliable:
        lines.append("")
        lines.append("⛔ AFFIDABILITÀ BASSA — dati critici insufficienti (servono almeno 5/7).")
        lines.append("   Il verdetto NON è un consiglio di acquisto.")
        lines.append(PAGES_GUIDE.strip())
    lines.append("")
    lines.append("📋 SUDDIVISIONE PUNTEGGIO:")
    for c in cats:
        lines.append(f"• {c.name}: {c.points:.0f}/{c.max_points}")
        for nte in c.notes[:3]:
            if nte:
                lines.append(f"    – {nte}")
    lines.append("")
    lines.append("📊 DATI ANALISTI:")
    lines.append(f"• Analisti: {n or tot_a or 'N/D'} | Affidabilità: {'ALTA' if (n or tot_a) >= 5 else 'BASSA'}")
    lines.append(f"• Consensus: {cons}")
    lines.append(f"• Target Medio: {fmt_num(m.get('target'))}" + (f" ({up:+.1f}%)" if up is not None else ""))
    lines.append("")
    lines.append("🏛️ SMART MONEY (istituzionali Yahoo):")
    lines.append(f"• Institutional: {fmt_num(m.get('inst'), '%')} | Short: {fmt_num(m.get('short_pct'), '%')} | Short ratio: {fmt_num(m.get('short_ratio'))}")
    lines.append("")
    lines.append("🧠 SUPERINVESTORS 13F (Dataroma — solo conferma):")
    lines.append(f"• Bonus applicato: {sm.bonus:+.0f} / +3 (mai sovrascrive EVITA)")
    if sm.source_url:
        lines.append(f"• Fonte: {sm.source_url}")
    for nte in sm.notes[:8]:
        lines.append(f"  – {nte}")
    if sm.error and not sm.holders:
        lines.append(f"  – {sm.error}")
    lines.append("  ⚠ 13F in ritardo ~45gg; prezzo ingresso loro ≠ tuo; non copiare trader (Burry/ARK).")
    lines.append("")
    lines.append("💵 CASH FLOW:")
    fcf_note = ""
    if m.get("fcf_source") == "ocf-capex":
        fcf_note = " (da OCF−CapEx)"
    elif m.get("fcf_source") == "fcf-row":
        fcf_note = " (riga Free Cash Flow)"
    elif m.get("fcf_source"):
        fcf_note = f" ({m.get('fcf_source')})"
    lines.append(
        f"• OCF: {fmt_money(m.get('ocf'))} | CapEx: {fmt_money(m.get('capex'))} | "
        f"FCF: {fmt_money(m.get('fcf'))}{fcf_note} | FCF Yield: {fmt_num(m.get('fcf_yield'), '%')}"
    )
    if m.get("fcf_margin") is not None:
        lines.append(f"• FCF Margin: {fmt_num(m.get('fcf_margin'), '%')}" + (f" | Rule of 40: {fmt_num(m.get('rule_of_40'))}" if m.get("rule_of_40") is not None else ""))
    lines.append("")
    lines.append(f"🎯 BUY TARGET: {target_txt}")
    lines.append(f"🔗 https://finance.yahoo.com/quote/{ticker} | https://finance.yahoo.com/quote/{ticker}/key-statistics")
    lines.append(f"🔗 https://finance.yahoo.com/quote/{ticker}/analysis | https://tikr.com/company/{ticker}")
    lines.append("")
    lines.append(f"🚩 RED FLAGS: [{len(flags)}] — {'; '.join(flags) if flags else 'nessuna'}")
    lines.append("")
    lines.append("⚠️ SE MANCANO DATI:")
    lines.append("1. Verifica ticker Yahoo (API automatica)")
    lines.append("2. Carica HTML Investing più completo")
    keys = SECTOR_KEY_METRICS.get(sector, [])
    if keys:
        lines.append(f"3. TIKR / report per: {', '.join(keys[:3])}")
    else:
        lines.append("3. Aggiungi TIKR (Z-Score, CAGR, quality)")
    lines.append("4. Opzionali: Finviz, MarketWatch, GuruFocus, TipRanks, Morningstar")
    lines.append("")
    lines.append(f"📢 VERDETTO FINALE: {verdict}")
    if not reliable:
        lines.append("   Motivo: troppi campi critici assenti. Controlla ticker + HTML Investing/TIKR.")
    else:
        lines.append(f"   Voto {total:.0f}/100 su settore {sector}.")
    lines.append("═══════════════════════════════════════")

    return {
        "report": "\n".join(lines),
        "score": total,
        "base_score": base_total,
        "smart_money_bonus": sm.bonus,
        "verdict": verdict,
        "risk": risk,
        "reliable": reliable,
        "coverage": cov,
        "metrics": m,
        "sector": sector,
        "smart_money": smart_money_to_dict(sm),
        "categories": [{"name": c.name, "points": c.points, "max": c.max_points} for c in cats],
    }
