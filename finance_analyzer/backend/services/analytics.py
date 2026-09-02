"""Historical performance metrics from price series."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd


def annual_return_cagr(prices: pd.Series) -> float | None:
    if len(prices) < 2:
        return None
    start = float(prices.iloc[0])
    end = float(prices.iloc[-1])
    if start <= 0:
        return None
    days = (prices.index[-1] - prices.index[0]).days
    if days < 30:
        return None
    years = days / 365.25
    cagr = (end / start) ** (1 / years) - 1
    return round(cagr * 100, 2)


def ytd_return(prices: pd.Series) -> float | None:
    if prices.empty:
        return None
    year = datetime.now().year
    year_prices = prices[prices.index.year == year]
    if len(year_prices) < 2:
        # Use last price of previous year as start
        prev = prices[prices.index.year < year]
        if prev.empty:
            return None
        start_price = float(prev.iloc[-1])
        end_price = float(prices.iloc[-1])
    else:
        start_price = float(year_prices.iloc[0])
        end_price = float(year_prices.iloc[-1])
    if start_price <= 0:
        return None
    return round(((end_price / start_price) - 1) * 100, 2)


def volatility_annual(prices: pd.Series) -> float | None:
    if len(prices) < 20:
        return None
    log_returns = np.log(prices / prices.shift(1)).dropna()
    if log_returns.empty:
        return None
    return round(float(log_returns.std() * np.sqrt(252) * 100), 2)


def max_drawdown(prices: pd.Series) -> float | None:
    if prices.empty:
        return None
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return round(float(drawdown.min() * 100), 2)


def chart_data(prices: pd.Series, max_points: int = 500) -> list[dict]:
    """Downsample for frontend chart."""
    if max_points <= 0:
        return []
    s = prices.dropna()
    if len(s) > max_points:
        step = len(s) // max_points
        s = s.iloc[::step]
    return [
        {"date": d.strftime("%Y-%m-%d"), "close": round(float(v), 4)}
        for d, v in s.items()
    ]
