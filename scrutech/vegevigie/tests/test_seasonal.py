"""Deseasonalization tests — the seasonal swing is removed, the trend slope survives."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.seasonal import deseasonalize, has_multiple_years


def _series(n_years: int) -> xr.DataArray:
    t = pd.date_range("2018-01-01", periods=12 * n_years, freq="MS")
    months = t.month.to_numpy()
    season = 0.3 * np.sin(2 * np.pi * (months - 1) / 12)  # strong seasonal swing
    trend = np.linspace(0.0, 0.1, len(t))  # gentle upward trend
    return xr.DataArray(season + trend, dims=("time",), coords={"time": t}, name="ndvi")


def test_deseasonalize_shrinks_seasonal_variance() -> None:
    raw = _series(3)
    anom = deseasonalize(raw)
    # The seasonal cycle is gone → far less variance, and each calendar month averages ~0.
    assert float(anom.std()) < float(raw.std())
    assert abs(float(anom.groupby("time.month").mean().mean())) < 1e-9


def test_deseasonalize_recovers_the_true_trend() -> None:
    raw = _series(3)
    anom = deseasonalize(raw)
    x = np.arange(raw.size)
    true_slope = 0.1 / (raw.size - 1)  # the injected linear trend
    # np.polyfit(x, y, 1) ajuste la droite (degré 1) qui passe "au mieux" par les
    # points (x, y) — la régression linéaire classique ; [0] prend son coefficient
    # directeur (la pente), [1] serait l'ordonnée à l'origine.
    slope_raw = np.polyfit(x, raw.to_numpy(), 1)[0]
    slope_anom = np.polyfit(x, anom.to_numpy(), 1)[0]
    # Deseasonalizing brings the estimated slope MUCH closer to the true trend.
    assert abs(slope_anom - true_slope) < abs(slope_raw - true_slope)
    assert np.isclose(slope_anom, true_slope, atol=5e-4)


def test_has_multiple_years() -> None:
    assert has_multiple_years(_series(2))
    assert not has_multiple_years(_series(1))
