"""Zonal aggregation tests — synthetic raster with known zones, no network (§8)."""

import geopandas as gpd
import numpy as np
import rioxarray  # noqa: F401 — registers the .rio accessor
import xarray as xr
from shapely.geometry import box

from vegevigie.zonal import (
    commune_stats,
    rasterize_zones,
    zonal_class_fraction,
    zonal_reduce,
)

# A 4x4 raster in a projected CRS spanning x,y in [0,4]; pixel size 1.
CRS = "EPSG:32631"


def _template() -> xr.DataArray:
    # Pixel centres at 0.5..3.5 so the grid covers [0,4] x [0,4].
    x = np.arange(0.5, 4, 1.0)
    y = np.arange(3.5, 0, -1.0)  # north-up (descending y)
    da = xr.DataArray(np.zeros((4, 4)), dims=("y", "x"), coords={"y": y, "x": x})
    return da.rio.write_crs(CRS)


def _two_communes() -> gpd.GeoDataFrame:
    # Left half (x 0-2) and right half (x 2-4).
    return gpd.GeoDataFrame(
        {"code": ["A", "B"], "nom": ["Left", "Right"]},
        geometry=[box(0, 0, 2, 4), box(2, 0, 4, 4)],
        crs=CRS,
    )


def test_rasterize_zones_splits_grid() -> None:
    zones = rasterize_zones(_two_communes(), _template())
    z = zones.values
    # Left two columns -> zone 0, right two -> zone 1.
    assert set(np.unique(z)) == {0, 1}
    assert (z[:, :2] == 0).all()
    assert (z[:, 2:] == 1).all()


def test_zonal_reduce_mean() -> None:
    template = _template()
    zones = rasterize_zones(_two_communes(), template)
    # Values: left half all 0.2, right half all 0.8.
    vals = template.copy()
    vals.values[:, :2] = 0.2
    vals.values[:, 2:] = 0.8
    means = zonal_reduce(vals, zones, n_zones=2, reducer="mean")
    assert np.allclose(means, [0.2, 0.8])


def test_zonal_reduce_nan_zone() -> None:
    template = _template()
    zones = rasterize_zones(_two_communes(), template)
    vals = template.copy()
    vals.values[:] = np.nan  # no valid pixels anywhere
    means = zonal_reduce(vals, zones, n_zones=2, reducer="mean")
    assert np.isnan(means).all()


def test_zonal_class_fraction() -> None:
    template = _template()
    zones = rasterize_zones(_two_communes(), template)
    classes = template.copy()
    # Left: all greening (1). Right: half greening, half no-trend (0).
    classes.values[:, :2] = 1
    classes.values[:2, 2:] = 1
    classes.values[2:, 2:] = 0
    pct = zonal_class_fraction(classes, zones, n_zones=2, target=1)
    assert np.isclose(pct[0], 100.0)
    assert np.isclose(pct[1], 50.0)


def test_commune_stats_columns_and_values() -> None:
    template = _template()
    communes = _two_communes()
    sen = template.copy()
    sen.values[:, :2] = 0.01  # left greening
    sen.values[:, 2:] = -0.02  # right browning
    tclass = template.copy()
    tclass.values[:, :2] = 1
    tclass.values[:, 2:] = -1

    out = commune_stats(communes, sen, tclass)
    assert {"mean_sen_slope", "pct_greening", "pct_browning"} <= set(out.columns)
    left = out[out["code"] == "A"].iloc[0]
    right = out[out["code"] == "B"].iloc[0]
    assert np.isclose(left["mean_sen_slope"], 0.01)
    assert np.isclose(left["pct_greening"], 100.0)
    assert np.isclose(right["pct_browning"], 100.0)
