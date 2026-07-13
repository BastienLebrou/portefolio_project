"""Drought-stat tests — pure functions on synthetic monthly cubes, no network (§8)."""

import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.drought import (
    drought_dataset,
    drought_timeline,
    monthly_climatology,
    ndvi_anomaly,
    vci,
)


def _monthly_cube(years: int, size: int = 2, builder=None) -> xr.DataArray:
    """A (years*12, size, size) monthly NDVI cube on a real month-start axis."""
    n = years * 12
    times = pd.date_range("2015-01-01", periods=n, freq="MS")
    if builder is None:
        # Pure seasonal cycle, identical every year.
        month = times.month.to_numpy()
        base = 0.55 + 0.2 * np.sin(2 * np.pi * (month - 4) / 12)
        data = np.repeat(base[:, None, None], size, axis=1).repeat(size, axis=2)
    else:
        data = builder(times, size)
    return xr.DataArray(
        data,
        dims=("time", "y", "x"),
        coords={"time": times, "y": np.arange(size), "x": np.arange(size)},
        name="ndvi_monthly",
    )


def test_climatology_shape_and_values() -> None:
    cube = _monthly_cube(years=5)
    clim = monthly_climatology(cube)
    assert clim["clim_mean"].sizes == {"month": 12, "y": 2, "x": 2}
    # Identical every year -> std 0, mean == the seasonal value, min == max.
    assert np.allclose(clim["clim_std"].values, 0.0)
    assert np.allclose(clim["clim_min"].values, clim["clim_max"].values)


def test_anomaly_zero_when_equal_to_climatology_mean() -> None:
    # Constant-history pixels have std 0 -> anomaly is NaN, not 0/inf.
    cube = _monthly_cube(years=4)
    clim = monthly_climatology(cube)
    anom = ndvi_anomaly(cube, clim)
    assert bool(np.isnan(anom).all())


def test_anomaly_zscore_known_values() -> None:
    # Build a pixel whose Januaries are [0.4, 0.6] over 2 years: mean 0.5, std 0.1.
    def builder(times, size):
        data = np.full((len(times), size, size), 0.5)
        jan = times.month == 1
        jan_idx = np.where(jan)[0]
        data[jan_idx[0]] = 0.4
        data[jan_idx[1]] = 0.6
        return data

    cube = _monthly_cube(years=2, builder=builder)
    clim = monthly_climatology(cube)
    anom = ndvi_anomaly(cube, clim)
    jan_anoms = anom.isel(time=[0, 12]).isel(y=0, x=0).values
    # z = (0.4-0.5)/0.1 = -1 ; (0.6-0.5)/0.1 = +1
    assert np.allclose(sorted(jan_anoms), [-1.0, 1.0])


def test_vci_bounds_and_endpoints() -> None:
    # Januaries [0.4, 0.6]: min 0.4 -> VCI 0, max 0.6 -> VCI 100.
    def builder(times, size):
        data = np.full((len(times), size, size), 0.5)
        jan_idx = np.where(times.month == 1)[0]
        data[jan_idx[0]] = 0.4
        data[jan_idx[1]] = 0.6
        return data

    cube = _monthly_cube(years=2, builder=builder)
    clim = monthly_climatology(cube)
    v = vci(cube, clim).isel(time=[0, 12]).isel(y=0, x=0).values
    assert np.allclose(sorted(v), [0.0, 100.0])
    all_vci = vci(cube, clim).values
    finite = all_vci[np.isfinite(all_vci)]
    assert finite.min() >= 0.0 and finite.max() <= 100.0


def test_dry_year_has_negative_anomaly() -> None:
    # Three normal years + one depressed year -> that year's anomaly is negative.
    def builder(times, size):
        month = times.month.to_numpy()
        base = 0.6 + 0.15 * np.sin(2 * np.pi * (month - 4) / 12)
        data = np.repeat(base[:, None, None], size, axis=1).repeat(size, axis=2)
        dry = np.asarray(times.year == 2018)
        data[dry] -= 0.12  # drought year
        return data

    cube = _monthly_cube(years=4, builder=builder)
    clim = monthly_climatology(cube)
    timeline = drought_timeline(ndvi_anomaly(cube, clim))
    dry_mean = timeline.sel(time=timeline["time"].dt.year == 2018).mean().item()
    wet_mean = timeline.sel(time=timeline["time"].dt.year != 2018).mean().item()
    assert dry_mean < 0 < wet_mean or dry_mean < wet_mean
    assert dry_mean < -0.5  # clearly a dry signal


def test_drought_dataset_structure() -> None:
    cube = _monthly_cube(years=3)
    ds = drought_dataset(cube)
    assert set(ds.data_vars) == {"ndvi_anomaly", "vci"}
    assert ds["ndvi_anomaly"].dims == ("time", "y", "x")
