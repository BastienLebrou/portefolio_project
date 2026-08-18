"""Deseasonalize a monthly NDVI series before the trend test — the robustness fix.

WHY. Mann-Kendall / Sen (see :mod:`vegevigie.trend`) assume the series has no strong
seasonal cycle. On raw monthly NDVI the summer/winter swing is huge and inflates the
variance, drowning a real multi-year trend (and, on gappy series, biasing it). The standard
answer is STL — decompose into *seasonal + trend + residual* and test the trend part. Full
STL needs ``statsmodels``; here we do the practical, dependency-free equivalent for a monthly
grid: subtract the **mean seasonal cycle** (per calendar month across years), leaving the
deseasonalized anomaly. Subtracting a per-month constant does not change the Sen slope, but it
removes the seasonal variance, so Mann-Kendall detects the trend far more reliably.

Only meaningful with **≥ 2 years** (with one year the climatology *is* each value → anomalies
are all zero); the pipeline guards on that.
"""

from __future__ import annotations

import xarray as xr


def deseasonalize(monthly: xr.DataArray, time_dim: str = "time") -> xr.DataArray:
    """Return the monthly anomaly: value − mean-for-that-calendar-month (across years).

    Pixel-wise, lazy on a dask-backed cube. Keeps the array name.
    """
    climatology = monthly.groupby(f"{time_dim}.month").mean(time_dim)
    anomaly = monthly.groupby(f"{time_dim}.month") - climatology
    return anomaly.rename(monthly.name)


def has_multiple_years(monthly: xr.DataArray, time_dim: str = "time") -> bool:
    """True if the series spans ≥ 2 calendar years (else deseasonalizing zeroes it out)."""
    years = monthly[time_dim].dt.year
    return int(years.max() - years.min()) >= 1
