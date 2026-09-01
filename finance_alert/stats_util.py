"""Statistiche robuste per baseline volume (outlier-resistant)."""

from __future__ import annotations

import statistics


def robust_average(values: list[float], *, trim_pct: float = 0.1) -> float:
    """Mediana se pochi campioni, altrimenti media trimmed (default 10% per estremi)."""
    clean = [float(v) for v in values if v and v > 0]
    if not clean:
        return 0.0
    if len(clean) < 5:
        return float(statistics.median(clean))
    ordered = sorted(clean)
    trim = max(1, int(len(ordered) * trim_pct))
    if len(ordered) <= trim * 2:
        return float(statistics.median(ordered))
    trimmed = ordered[trim:-trim]
    return sum(trimmed) / len(trimmed)
