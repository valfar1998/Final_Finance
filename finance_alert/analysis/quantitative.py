"""Quantitative analysis — prefer Finance-Analyzer backend when available."""

from __future__ import annotations

from typing import Any

import yfinance as yf


def _via_fin_analyzer(ticker: str) -> dict[str, Any] | None:
    try:
        from finance_alert.analysis.bridge import ensure_fin_analyzer

        ensure_fin_analyzer()
        from services.analytics import (  # type: ignore
            annual_return_cagr,
            max_drawdown,
            volatility_annual,
            ytd_return,
        )
        from services.forecast import monte_carlo_forecast  # type: ignore
        from services.market_data import get_close_prices, get_analyst_buyability  # type: ignore

        stooq = f"{ticker.lower()}.us" if "." not in ticker else ticker.lower()
        prices, _src = get_close_prices(stooq, ticker)
        cagr = annual_return_cagr(prices)
        vol = volatility_annual(prices)
        mdd = max_drawdown(prices)
        ytd = ytd_return(prices)
        forecast = monte_carlo_forecast(prices, simulations=2000, horizon_days=30)
        current = forecast.get("current_price")
        analyst = get_analyst_buyability(ticker, "azione", current_price=current)
        qscore = quant_score_from_metrics(cagr, vol, mdd)
        return {
            "ticker": ticker.upper(),
            "cagr_pct": cagr,
            "volatility_pct": vol,
            "max_drawdown_pct": mdd,
            "ytd_pct": ytd,
            "quant_score": qscore,
            "monte_carlo": {
                "forecast_price": forecast.get("forecast_price"),
                "forecast_low": forecast.get("forecast_low"),
                "forecast_high": forecast.get("forecast_high"),
            },
            "buyability_pct": analyst.get("buyability_pct"),
            "analyst_target": analyst.get("analyst_target_mean"),
            "current_price": current,
            "_source": "finance-analyzer",
        }
    except Exception:
        return None


def quant_score_from_metrics(cagr: float | None, vol: float | None, max_dd: float | None) -> float:
    score = 5.0
    if cagr is not None:
        if cagr > 15:
            score += 2.0
        elif cagr > 5:
            score += 1.0
        elif cagr < -5:
            score -= 2.0
    if vol is not None:
        if vol < 25:
            score += 1.0
        elif vol > 50:
            score -= 1.5
    if max_dd is not None:
        if max_dd > -25:
            score += 0.5
        elif max_dd < -50:
            score -= 1.5
    return max(0.0, min(10.0, score))


def _fetch_prices(ticker: str, period: str = "3y") -> list[float]:
    hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
    if hist is None or hist.empty:
        return []
    return [float(x) for x in hist["Close"].tolist() if x == x]


def _cagr(prices: list[float]) -> float | None:
    if len(prices) < 30:
        return None
    start, end = prices[0], prices[-1]
    if start <= 0:
        return None
    years = len(prices) / 252.0
    if years < 0.25:
        return None
    return round(((end / start) ** (1 / years) - 1) * 100, 2)


def _volatility(prices: list[float]) -> float | None:
    if len(prices) < 30:
        return None
    import math

    rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return round((var**0.5) * (252**0.5) * 100, 2)


def _max_dd(prices: list[float]) -> float | None:
    if not prices:
        return None
    peak = prices[0]
    worst = 0.0
    for p in prices:
        peak = max(peak, p)
        dd = (p - peak) / peak
        worst = min(worst, dd)
    return round(worst * 100, 2)


def _monte_carlo(prices: list[float], *, sims: int = 2000, horizon: int = 30) -> dict[str, float | None]:
    if len(prices) < 60:
        return {"forecast_price": None, "forecast_low": None, "forecast_high": None}
    import math
    import random

    rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices)) if prices[i - 1] > 0]
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / len(rets)
    sigma = var**0.5
    current = prices[-1]
    finals: list[float] = []
    rng = random.Random(42)
    for _ in range(sims):
        p = current
        for _ in range(horizon):
            p *= math.exp(rng.gauss(mu, sigma))
        finals.append(p)
    finals.sort()
    return {
        "forecast_price": round(finals[len(finals) // 2], 2),
        "forecast_low": round(finals[int(len(finals) * 0.1)], 2),
        "forecast_high": round(finals[int(len(finals) * 0.9)], 2),
    }


def analyze_quantitative(ticker: str) -> dict[str, Any]:
    fa = _via_fin_analyzer(ticker)
    if fa:
        return fa
    prices = _fetch_prices(ticker)
    cagr = _cagr(prices)
    vol = _volatility(prices)
    max_dd = _max_dd(prices)
    mc = _monte_carlo(prices)
    qscore = quant_score_from_metrics(cagr, vol, max_dd)
    return {
        "ticker": ticker.upper(),
        "cagr_pct": cagr,
        "volatility_pct": vol,
        "max_drawdown_pct": max_dd,
        "quant_score": qscore,
        "monte_carlo": mc,
        "current_price": prices[-1] if prices else None,
        "_source": "yfinance-fallback",
    }
