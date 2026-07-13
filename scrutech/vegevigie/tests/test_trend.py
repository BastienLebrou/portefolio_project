"""Trend tests — the vectorized MK+Sen kernel must match pymannkendall (§5/§8)."""

import numpy as np
import pymannkendall as pmk
import pytest
import xarray as xr

from vegevigie.trend import BROWNING, GREENING, NO_TREND, mk_sen_1d, trend_dataset

# A spread of series: clear greening, browning, flat+noise, with ties, and NaNs.
SAMPLE_SERIES = {
    "greening": np.linspace(0.3, 0.8, 24) + np.sin(np.arange(24)) * 0.01,
    "browning": np.linspace(0.85, 0.4, 30),
    "noisy_flat": np.array([0.5, 0.52, 0.48, 0.51, 0.49, 0.5, 0.53, 0.47, 0.5, 0.51, 0.49, 0.5]),
    "with_ties": np.array([0.4, 0.4, 0.5, 0.5, 0.6, 0.6, 0.6, 0.7, 0.7, 0.8]),
    "seasonal_rise": (
        0.55 + 0.2 * np.sin(2 * np.pi * np.arange(48) / 12) + np.linspace(0, 0.15, 48)
    ),
}


@pytest.mark.parametrize("name", list(SAMPLE_SERIES))
def test_matches_pymannkendall_clean_series(name: str) -> None:
    y = SAMPLE_SERIES[name]
    slope, p, z, tclass = mk_sen_1d(y, alpha=0.05, min_valid=4)

    ref = pmk.original_test(y, alpha=0.05)
    ref_slope = pmk.sens_slope(y).slope

    assert np.isclose(p, ref.p, atol=1e-9)
    assert np.isclose(z, ref.z, atol=1e-9)
    assert np.isclose(slope, ref_slope, atol=1e-9)

    expected_class = {"increasing": GREENING, "decreasing": BROWNING, "no trend": NO_TREND}[
        ref.trend
    ]
    assert tclass == expected_class


def test_matches_pymannkendall_with_nan_gaps() -> None:
    # pymannkendall skips NaNs for MK and uses original positions for the slope;
    # our kernel must reproduce both on the same gappy series.
    y = np.array([0.3, np.nan, 0.4, 0.45, np.nan, 0.55, 0.6, 0.7, np.nan, 0.8])
    slope, p, z, _ = mk_sen_1d(y, alpha=0.05, min_valid=4)

    ref = pmk.original_test(y, alpha=0.05)
    ref_slope = pmk.sens_slope(y).slope
    assert np.isclose(p, ref.p, atol=1e-9)
    assert np.isclose(z, ref.z, atol=1e-9)
    assert np.isclose(slope, ref_slope, atol=1e-9)


def test_insufficient_data_returns_nan() -> None:
    y = np.array([0.5, np.nan, np.nan, 0.6])
    result = mk_sen_1d(y, min_valid=6)
    assert all(np.isnan(v) for v in result)


def test_greening_and_browning_classes() -> None:
    up = mk_sen_1d(np.linspace(0.2, 0.9, 20))
    down = mk_sen_1d(np.linspace(0.9, 0.2, 20))
    assert up[3] == GREENING and up[0] > 0
    assert down[3] == BROWNING and down[0] < 0


def test_trend_dataset_over_cube() -> None:
    # 2x2 pixels: one greening, one browning, two flat.
    t = 24
    data = np.empty((t, 2, 2))
    data[:, 0, 0] = np.linspace(0.3, 0.8, t)  # greening
    data[:, 0, 1] = np.linspace(0.8, 0.3, t)  # browning
    data[:, 1, 0] = 0.5  # flat
    data[:, 1, 1] = 0.5  # flat
    da = xr.DataArray(data, dims=("time", "y", "x"))

    out = trend_dataset(da, alpha=0.05, min_valid=4)
    assert set(out.data_vars) == {"sen_slope", "mk_pvalue", "mk_z", "trend_class"}
    assert out["sen_slope"].shape == (2, 2)
    assert out["trend_class"].sel(y=0, x=0).item() == GREENING
    assert out["trend_class"].sel(y=0, x=1).item() == BROWNING
    assert out["trend_class"].values.ravel().tolist().count(NO_TREND) == 2


def test_trend_dataset_lazy_with_dask() -> None:
    t = 24
    da = xr.DataArray(
        np.linspace(0.3, 0.8, t)[:, None, None].repeat(2, 1).repeat(2, 2),
        dims=("time", "y", "x"),
    ).chunk({"y": 1, "x": 1})
    out = trend_dataset(da, min_valid=4)
    # Still lazy before compute.
    assert out["sen_slope"].chunks is not None
    computed = out.compute()
    assert bool((computed["trend_class"] == GREENING).all())
