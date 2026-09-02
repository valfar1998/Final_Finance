"""Bridge opzionale a librerie Asia (locale) — AKShare / TuShare / FinanceDataReader / PyKRX.

Non richiesto da GitHub Actions. Installa con:
  pip install -r requirements-asia.txt

OpenDART (filings KR) è nel core (`regulatory/opendart.py`) e aspetta OPEN_DART_API_KEY.
EODHD (quote multi-mercato) è nel core (`sources/eodhd.py`) con EODHD_API_TOKEN.
"""

from __future__ import annotations

from typing import Any


def status() -> dict[str, bool]:
    return {
        "akshare": _has("akshare"),
        "tushare": _has("tushare") and bool(_tushare_token()),
        "finance_data_reader": _has("FinanceDataReader"),
        "pykrx": _has("pykrx"),
    }


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def _tushare_token() -> str:
    import os

    return (os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_KEY") or "").strip()


def akshare_szse_summary(date: str = "") -> Any | None:
    """Esempio AKShare: riepilogo Shenzhen (date YYYYMMDD)."""
    if not _has("akshare"):
        return None
    import akshare as ak  # type: ignore

    if not date:
        from datetime import date as _date

        date = _date.today().strftime("%Y%m%d")
    return ak.stock_szse_summary(date=date)


def akshare_spot_a_shares(limit: int = 20) -> list[dict[str, Any]]:
    """Snapshot A-shares (spot EM) — solo locale, può essere lento."""
    if not _has("akshare"):
        return []
    import akshare as ak  # type: ignore

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        return []
    if df is None or getattr(df, "empty", True):
        return []
    rows = df.head(limit).to_dict(orient="records")
    return rows if isinstance(rows, list) else []


def tushare_daily(ts_code: str, start: str = "", end: str = "") -> Any | None:
    """TuShare Pro daily bar. ts_code es. 600519.SH, 000001.SZ."""
    token = _tushare_token()
    if not token or not _has("tushare"):
        return None
    import tushare as ts  # type: ignore

    pro = ts.pro_api(token)
    kwargs: dict[str, str] = {"ts_code": ts_code}
    if start:
        kwargs["start_date"] = start.replace("-", "")
    if end:
        kwargs["end_date"] = end.replace("-", "")
    try:
        return pro.daily(**kwargs)
    except Exception:
        return None


def fdr_kr_ohlcv(ticker: str, start: str = "2024-01-01", end: str | None = None) -> Any | None:
    """FinanceDataReader — storici KRX. ticker es. 005930 (senza .KS)."""
    if not _has("FinanceDataReader"):
        return None
    import FinanceDataReader as fdr  # type: ignore

    code = ticker.upper().replace(".KS", "").replace(".KQ", "")
    try:
        return fdr.DataReader(code, start, end)
    except Exception:
        return None


def pykrx_ohlcv(ticker: str, start: str, end: str) -> Any | None:
    """PyKRX — OHLCV dal portale KRX. date YYYYMMDD."""
    if not _has("pykrx"):
        return None
    from pykrx import stock  # type: ignore

    code = ticker.upper().replace(".KS", "").replace(".KQ", "")
    start_s = start.replace("-", "")
    end_s = end.replace("-", "")
    try:
        return stock.get_market_ohlcv_by_date(start_s, end_s, code)
    except Exception:
        return None


def pykrx_fundamental(ticker: str, date: str) -> dict[str, Any]:
    """PER/PBR/DIV per data (YYYYMMDD) via PyKRX."""
    if not _has("pykrx"):
        return {}
    from pykrx import stock  # type: ignore

    code = ticker.upper().replace(".KS", "").replace(".KQ", "")
    d = date.replace("-", "")
    out: dict[str, Any] = {"ticker": code, "date": d}
    try:
        fund = stock.get_market_fundamental_by_date(d, d, code)
        if fund is not None and not fund.empty:
            for c in fund.columns:
                try:
                    out[str(c)] = float(fund[c].iloc[-1])
                except (TypeError, ValueError, IndexError):
                    continue
    except Exception:
        pass
    return out
