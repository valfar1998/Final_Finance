#!/usr/bin/env python3
"""Fetch metriche Yahoo Finance via yfinance (niente HTML)."""
from __future__ import annotations

import re
from typing import Any

import yfinance as yf


TICKER_RE = re.compile(
    r"^[A-Za-z0-9]{1,6}(?:[.\-][A-Za-z0-9]{1,5})?$"
)


def normalize_ticker(raw: str) -> str:
    t = (raw or "").strip().upper().replace(" ", "")
    if not t or not TICKER_RE.match(t):
        raise ValueError(
            f"Ticker non valido: {raw!r} "
            "(es. GOOGL, BRK-B, BMW.DE, BREN.JK, 285A.T, 7203.T)"
        )
    return t


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _pct(v: Any, *, assume_ratio_if_abs_le_1: bool = True) -> float | None:
    """Converte yield/growth/margins in percentuale (es. 0.25 → 25)."""
    f = _num(v)
    if f is None:
        return None
    if assume_ratio_if_abs_le_1 and abs(f) <= 1.0:
        return f * 100.0
    return f


def _debt_equity(v: Any) -> float | None:
    """Yahoo info debtToEquity è spesso in % (es. 37.5 = 0.375)."""
    f = _num(v)
    if f is None:
        return None
    if f > 5:
        return f / 100.0
    return f


def _rec_counts(ticker: yf.Ticker) -> dict[str, float | None]:
    out: dict[str, float | None] = {
        "strong_buy": None,
        "buy": None,
        "hold": None,
        "sell": None,
        "strong_sell": None,
        "n_analysts": None,
    }
    df = None
    for attr in ("recommendations_summary", "recommendations"):
        try:
            df = getattr(ticker, attr, None)
        except Exception:
            df = None
        if df is not None and hasattr(df, "empty") and not df.empty:
            break
        df = None

    if df is None:
        return out

    # recommendations_summary: index o colonna "period" con riga 0m
    try:
        row = df.iloc[0]
        cols = {str(c).strip().lower(): c for c in df.columns}

        def get(*names: str) -> float | None:
            for n in names:
                if n.lower() in cols:
                    return _num(row[cols[n.lower()]])
            # a volte le label sono nell'indice
            return None

        # Formato tipico: strongBuy, buy, hold, sell, strongSell
        sb = get("strongBuy", "strong buy")
        b = get("buy")
        h = get("hold")
        s = get("sell")
        ss = get("strongSell", "strong sell")

        # Formato recommendations storico: To Grade counts — skip se non ha i campi
        if any(x is not None for x in (sb, b, h, s, ss)):
            out["strong_buy"] = sb or 0.0
            out["buy"] = b or 0.0
            out["hold"] = h or 0.0
            out["sell"] = s or 0.0
            out["strong_sell"] = ss or 0.0
            total = out["strong_buy"] + out["buy"] + out["hold"] + out["sell"] + out["strong_sell"]
            if 1 <= total <= 80:
                out["n_analysts"] = total
            else:
                out["strong_buy"] = out["buy"] = out["hold"] = out["sell"] = out["strong_sell"] = None
    except Exception:
        pass
    return out


def fetch_yahoo_metrics(ticker: str) -> dict[str, Any]:
    """
    Restituisce un dict compatibile con scoring_engine (stesse chiavi di extract_metrics).
    Solleva ValueError / RuntimeError se ticker assente o dati vuoti.
    """
    sym = normalize_ticker(ticker)
    t = yf.Ticker(sym)

    info: dict[str, Any] = {}
    try:
        info = t.info or {}
    except Exception as exc:
        raise RuntimeError(f"Yahoo Finance non raggiungibile per {sym}: {exc}") from exc

    if not info or (info.get("trailingPegRatio") is None and info.get("regularMarketPrice") is None and info.get("currentPrice") is None and not info.get("symbol")):
        # secondo tentativo: fast_info
        try:
            fi = t.fast_info
            info = {
                "symbol": sym,
                "shortName": getattr(fi, "shortName", None) or sym,
                "regularMarketPrice": getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None),
                "marketCap": getattr(fi, "market_cap", None) or getattr(fi, "marketCap", None),
                "fiftyDayAverage": getattr(fi, "fifty_day_average", None),
                "twoHundredDayAverage": getattr(fi, "two_hundred_day_average", None),
            }
        except Exception:
            pass

    price = _num(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
    if price is None:
        raise RuntimeError(
            f"Nessun dato Yahoo per '{sym}'. Controlla il ticker "
            "(es. GOOGL non GOOG.L, BRK-B non BRK.B)."
        )

    name = info.get("longName") or info.get("shortName") or sym
    rec = _rec_counts(t)
    n_from_info = _num(info.get("numberOfAnalystOpinions"))
    if rec["n_analysts"] is None and n_from_info is not None and 1 <= n_from_info <= 80:
        rec["n_analysts"] = n_from_info

    # Target prices
    target = _num(info.get("targetMeanPrice"))
    target_low = _num(info.get("targetLowPrice"))
    target_high = _num(info.get("targetHighPrice"))
    try:
        apt = t.analyst_price_targets
        if isinstance(apt, dict):
            target = target or _num(apt.get("mean") or apt.get("current"))
            target_low = target_low or _num(apt.get("low"))
            target_high = target_high or _num(apt.get("high"))
    except Exception:
        pass

    inst = _pct(info.get("heldPercentInstitutions"))
    short_pct = _pct(info.get("shortPercentOfFloat"))
    # growth / margins: yfinance di solito in ratio
    rev_growth = _pct(info.get("revenueGrowth"))
    eps_growth = _pct(info.get("earningsQuarterlyGrowth"))
    gross_m = _pct(info.get("grossMargins"))
    op_m = _pct(info.get("operatingMargins"))
    net_m = _pct(info.get("profitMargins"))
    roe = _pct(info.get("returnOnEquity"))
    roa = _pct(info.get("returnOnAssets"))
    div_yield = _pct(info.get("dividendYield") or info.get("trailingAnnualDividendYield"))
    payout = _pct(info.get("payoutRatio"))
    week52 = _pct(info.get("52WeekChange") or info.get("fiftyTwoWeekChange"), assume_ratio_if_abs_le_1=True)

    if div_yield is not None and div_yield > 30:
        div_yield = None
    if payout is not None and payout > 500:
        payout = None

    fcf = _num(info.get("freeCashflow"))
    ocf = _num(info.get("operatingCashflow"))
    capex = None

    # Fallback: statement Yahoo cashflow (Free Cash Flow / OCF − CapEx)
    if fcf is None or ocf is None:
        try:
            cf_df = getattr(t, "cashflow", None)
            if cf_df is not None and hasattr(cf_df, "empty") and not cf_df.empty:
                def _cf_row(*names: str) -> float | None:
                    for idx in cf_df.index:
                        label = str(idx).lower()
                        for name in names:
                            if name in label:
                                try:
                                    return _num(cf_df.loc[idx].iloc[0])
                                except Exception:
                                    return None
                    return None

                if ocf is None:
                    ocf = _cf_row("operating cash flow", "total cash from operating activities")
                if capex is None:
                    capex = _cf_row("capital expenditure", "capital expenditures")
                if fcf is None:
                    fcf = _cf_row("free cash flow")
                if fcf is None and ocf is not None and capex is not None:
                    # CapEx Yahoo di solito negativo
                    fcf = ocf + capex if capex < 0 else ocf - abs(capex)
        except Exception:
            pass

    revenue = _num(info.get("totalRevenue"))
    ebitda = _num(info.get("ebitda"))
    fcf_margin = None
    if fcf is not None and revenue and revenue > 0:
        fcf_margin = (fcf / revenue) * 100.0
    ebitda_m = None
    if ebitda is not None and revenue and revenue > 0:
        ebitda_m = (ebitda / revenue) * 100.0
    rule40 = None
    if rev_growth is not None and fcf_margin is not None:
        rule40 = rev_growth + fcf_margin

    return {
        "ticker": sym,
        "name": name,
        "price": price,
        "market_cap": _num(info.get("marketCap")),
        "pe": _num(info.get("trailingPE")),
        "forward_pe": _num(info.get("forwardPE")),
        "peg": _num(info.get("pegRatio") or info.get("trailingPegRatio")),
        "pb": _num(info.get("priceToBook")),
        "ps": _num(info.get("priceToSalesTrailing12Months")),
        "ev_ebitda": _num(info.get("enterpriseToEbitda")),
        "eps": _num(info.get("trailingEps")),
        "forward_eps": _num(info.get("forwardEps")),
        "eps_growth": eps_growth,
        "de": _debt_equity(info.get("debtToEquity")),
        "current_ratio": _num(info.get("currentRatio")),
        "interest_cov": None,
        "altman": None,
        "fcf": fcf,
        "ocf": ocf,
        "capex": abs(capex) if capex is not None else None,
        "net_income": _num(info.get("netIncomeToCommon")),
        "revenue": revenue,
        "ebitda": ebitda,
        "fcf_margin": fcf_margin,
        "ebitda_m": ebitda_m,
        "rule_of_40": rule40,
        "div_yield": div_yield,
        "payout": payout,
        "rev_growth": rev_growth,
        "rev_cagr_3y": None,
        "gross_m": gross_m,
        "op_m": op_m,
        "net_m": net_m,
        "roe": roe,
        "roa": roa,
        "beta": _num(info.get("beta")),
        "sma50": _num(info.get("fiftyDayAverage")),
        "sma200": _num(info.get("twoHundredDayAverage")),
        "rsi": None,
        "week52": week52,
        "avg_vol": _num(info.get("averageVolume") or info.get("averageDailyVolume10Day")),
        "target": target,
        "target_low": target_low,
        "target_high": target_high,
        "strong_buy": rec["strong_buy"],
        "buy": rec["buy"],
        "hold": rec["hold"],
        "sell": rec["sell"],
        "strong_sell": rec["strong_sell"],
        "n_analysts": rec["n_analysts"],
        "inst": inst,
        "short_pct": short_pct,
        "short_ratio": _num(info.get("shortRatio")),
        "ffo": None,
        "affo": None,
        "nav": None,
        "nav_premium": None,
        "debt_ebitda": None,
        "nii": None,
        "nii_coverage": None,
        "non_accrual": None,
        "ss_noi": None,
        "ss_sales": None,
        "cet1": None,
        "nim": None,
        "npl": None,
        "cost_income": None,
        "rd_rev": None,
        "roic": None,
        "book_to_bill": None,
        "capex_rev": None,
        "arpu": None,
        "churn": None,
        "inventory_turns": None,
        "bvps": _num(info.get("bookValue")),
        "shares": _num(info.get("sharesOutstanding")),
        "_source": "yfinance",
    }
