"""Monthly compositing tests — pure functions on synthetic cubes, no network (§8)."""

import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.composite import (
    build_monthly_ndvi,
    fill_temporal_gaps,
    monthly_median,
    valid_count_per_month,
)


def _cube(times: list[str], values: list[float]) -> xr.DataArray:
    """1x1-pixel NDVI cube with the given per-time values (NaN allowed)."""
    t = pd.to_datetime(times)
    data = np.array(values, dtype="float64").reshape(len(times), 1, 1)
    return xr.DataArray(data, dims=("time", "y", "x"), coords={"time": t, "y": [0], "x": [0]})


def test_monthly_median_takes_per_month_median() -> None:
    # January: 0.2, 0.4, 0.6 -> median 0.4 ; February: 0.5, 0.7 -> median 0.6
    cube = _cube(
        ["2020-01-05", "2020-01-15", "2020-01-25", "2020-02-10", "2020-02-20"],
        [0.2, 0.4, 0.6, 0.5, 0.7],
    )
    monthly = monthly_median(cube)
    assert monthly.sizes["time"] == 2
    assert np.isclose(monthly.isel(time=0).item(), 0.4)
    assert np.isclose(monthly.isel(time=1).item(), 0.6)


def test_monthly_median_skips_nan() -> None:
    # One valid + one masked (NaN) in January -> median ignores the NaN.
    cube = _cube(["2020-01-05", "2020-01-20"], [0.8, np.nan])
    assert np.isclose(monthly_median(cube).isel(time=0).item(), 0.8)


def test_monthly_median_all_nan_month_is_gap() -> None:
    # A month with no valid observation must stay NaN, not be fabricated.
    cube = _cube(["2020-03-05", "2020-03-20"], [np.nan, np.nan])
    assert np.isnan(monthly_median(cube).isel(time=0).item())


def test_valid_count_per_month() -> None:
    cube = _cube(["2020-01-05", "2020-01-20", "2020-01-28"], [0.5, np.nan, 0.7])
    assert valid_count_per_month(cube).isel(time=0).item() == 2


def test_fill_temporal_gaps_fills_short_gap() -> None:
    # Jan=0.2, Feb=NaN, Mar=0.6 -> single-month gap filled to the midpoint 0.4.
    monthly = _cube(["2020-01-01", "2020-02-01", "2020-03-01"], [0.2, np.nan, 0.6])
    filled = fill_temporal_gaps(monthly, max_gap=1)
    assert np.isclose(filled.isel(time=1).item(), 0.4)


def test_fill_temporal_gaps_leaves_long_gap() -> None:
    # A 2-month gap with max_gap=1 stays NaN (we don't invent unobserved seasons).
    monthly = _cube(
        ["2020-01-01", "2020-02-01", "2020-03-01", "2020-04-01"],
        [0.2, np.nan, np.nan, 0.8],
    )
    filled = fill_temporal_gaps(monthly, max_gap=1)
    assert np.isnan(filled.isel(time=1).item())
    assert np.isnan(filled.isel(time=2).item())


def test_fill_max_gap_zero_is_noop() -> None:
    monthly = _cube(["2020-01-01", "2020-02-01"], [0.2, np.nan])
    filled = fill_temporal_gaps(monthly, max_gap=0)
    assert np.isnan(filled.isel(time=1).item())


def test_build_monthly_ndvi_composites_then_fills() -> None:
    cube = _cube(
        ["2020-01-05", "2020-01-25", "2020-03-10"],  # Feb entirely missing
        [0.2, 0.4, 0.8],
    )
    out = build_monthly_ndvi(cube, fill_max_gap=1)
    # Jan median 0.3, Feb gap filled at the equidistant midpoint of 0.3 and 0.8 =
    # 0.55, Mar 0.8
    assert np.isclose(out.isel(time=0).item(), 0.3)
    assert np.isclose(out.isel(time=1).item(), 0.55)
    assert np.isclose(out.isel(time=2).item(), 0.8)
