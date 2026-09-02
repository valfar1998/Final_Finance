"""Probabilistic price forecast from historical returns (Monte Carlo)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def monte_carlo_forecast(
    prices: pd.Series,
    horizon_days: int = 252,
    simulations: int = 5000,
    seed: int = 42,
) -> dict:
    """
    Log-normal Monte Carlo using historical daily log-returns.
    Returns median forecast, 10th/90th percentile range.
    """
    if len(prices) < 60:
        return {
            "forecast_price": None,
            "forecast_low": None,
            "forecast_high": None,
            "forecast_return_pct": None,
            "method": "monte_carlo",
            "note": "Dati insufficienti per simulazione",
        }

    log_returns = np.log(prices / prices.shift(1)).dropna().values
    mu = float(np.mean(log_returns))
    sigma = float(np.std(log_returns))
    current = float(prices.iloc[-1])

    rng = np.random.default_rng(seed)
    # Vectorized simulation
    shocks = rng.normal(mu, sigma, size=(simulations, horizon_days))
    paths = current * np.exp(np.cumsum(shocks, axis=1))
    final_prices = paths[:, -1]

    median = float(np.median(final_prices))
    low = float(np.percentile(final_prices, 10))
    high = float(np.percentile(final_prices, 90))
    ret_pct = ((median / current) - 1) * 100

    return {
        "forecast_price": round(median, 2),
        "forecast_low": round(low, 2),
        "forecast_high": round(high, 2),
        "forecast_return_pct": round(ret_pct, 2),
        "current_price": round(current, 2),
        "horizon_days": horizon_days,
        "simulations": simulations,
        "method": "monte_carlo_log_normal",
        "note": (
            f"Simulazione su {simulations} scenari basata su rendimenti storici. "
            "Non è una previsione certa."
        ),
    }
