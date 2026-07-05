"""Zonal aggregation — raster trend/drought stats summarized per commune.

The trend and drought products are per-pixel rasters (in the Sentinel-2 UTM grid);
decision-makers think in communes. This stage burns each commune polygon onto the
raster grid (a **zone index raster**) and reduces the pixel values falling inside
each commune to a handful of numbers:

- ``mean_sen_slope`` — average greening/browning rate (NDVI/month) in the commune;
- ``pct_greening`` / ``pct_browning`` — share of significantly trending pixels;
- ``mean_anomaly`` — average NDVI z-score (drought exposure; more negative = drier);
- ``min_vci`` — worst Vegetation Condition Index reached (lower = more stressed).

Rasterizing polygons onto the value grid (rather than vectorizing pixels) is the
cheap, standard way to do zonal stats at scale. Geometry is reprojected to the
raster CRS first. The reduction functions are pure NumPy and unit-tested offline.
"""

from __future__ import annotations

from collections.abc import Callable

import geopandas as gpd
import numpy as np
import xarray as xr
from rasterio.features import rasterize

NODATA_ZONE = -1


def rasterize_zones(communes: gpd.GeoDataFrame, template: xr.DataArray) -> xr.DataArray:
    """Burn commune polygons onto ``template``'s grid as integer zone indices.

    Zone index = the commune's row position in ``communes``; pixels outside every
    commune get :data:`NODATA_ZONE`. ``template`` must carry rioxarray CRS + coords.
    """
    crs = template.rio.crs
    projected = communes.to_crs(crs)
    transform = template.rio.transform()
    out_shape = (template.sizes["y"], template.sizes["x"])
    shapes = ((geom, idx) for idx, geom in enumerate(projected.geometry))
    zones = rasterize(
        shapes,
        out_shape=out_shape,
        transform=transform,
        fill=NODATA_ZONE,
        dtype="int32",
        all_touched=True,
    )
    return xr.DataArray(zones, dims=("y", "x"), coords={"y": template["y"], "x": template["x"]})


ZoneGroups = list[np.ndarray]


def zone_groups(zones: xr.DataArray, n_zones: int) -> ZoneGroups:
    """Group flat pixel indices by zone in one stable sort.

    Precomputing this once and reusing it across every statistic replaces one
    full-raster scan per (zone × statistic) with a single O(N log N) sort — the
    difference between seconds and minutes at department scale.
    """
    z = np.asarray(zones.values).ravel()
    order = np.argsort(z, kind="stable")
    sorted_z = z[order]
    starts = np.searchsorted(sorted_z, np.arange(n_zones), side="left")
    ends = np.searchsorted(sorted_z, np.arange(n_zones), side="right")
    return [order[s:e] for s, e in zip(starts, ends, strict=True)]


def zonal_reduce(
    values: xr.DataArray,
    zones: xr.DataArray,
    n_zones: int,
    reducer: str,
    groups: ZoneGroups | None = None,
) -> np.ndarray:
    """Reduce ``values`` per zone with ``reducer`` ('mean'|'min'|'max'), NaN-aware.

    Returns an array of length ``n_zones``; zones with no valid pixel yield NaN.
    Pass precomputed ``groups`` (from :func:`zone_groups`) to amortize the zone
    lookup across several statistics.
    """
    funcs: dict[str, Callable[[np.ndarray], np.floating]] = {
        "mean": np.nanmean,
        "min": np.nanmin,
        "max": np.nanmax,
    }
    fn = funcs[reducer]
    v = np.asarray(values.values, dtype="float64").ravel()
    if groups is None:
        groups = zone_groups(zones, n_zones)
    out = np.full(n_zones, np.nan)
    for idx, group in enumerate(groups):
        sel = v[group]
        if sel.size and np.isfinite(sel).any():
            out[idx] = fn(sel)
    return out


def zonal_class_fraction(
    classes: xr.DataArray,
    zones: xr.DataArray,
    n_zones: int,
    target: int,
    groups: ZoneGroups | None = None,
) -> np.ndarray:
    """Percentage of valid (non-NaN) class pixels equal to ``target``, per zone."""
    c = np.asarray(classes.values, dtype="float64").ravel()
    if groups is None:
        groups = zone_groups(zones, n_zones)
    out = np.full(n_zones, np.nan)
    for idx, group in enumerate(groups):
        sel = c[group]
        valid = sel[np.isfinite(sel)]
        if valid.size:
            out[idx] = 100.0 * np.count_nonzero(valid == target) / valid.size
    return out


def commune_stats(
    communes: gpd.GeoDataFrame,
    sen_slope: xr.DataArray,
    trend_class: xr.DataArray,
    mean_anomaly: xr.DataArray | None = None,
    min_vci: xr.DataArray | None = None,
) -> gpd.GeoDataFrame:
    """Aggregate per-pixel trend/drought rasters to per-commune statistics.

    All rasters must share the grid of ``sen_slope`` (which carries the CRS used to
    rasterize the communes). Returns ``communes`` plus the stat columns.
    """
    zones = rasterize_zones(communes, sen_slope)
    n = len(communes)
    groups = zone_groups(zones, n)  # one sort, shared by every statistic below

    out = communes.copy()
    out["mean_sen_slope"] = zonal_reduce(sen_slope, zones, n, "mean", groups)
    out["pct_greening"] = zonal_class_fraction(trend_class, zones, n, 1, groups)
    out["pct_browning"] = zonal_class_fraction(trend_class, zones, n, -1, groups)
    if mean_anomaly is not None:
        out["mean_anomaly"] = zonal_reduce(mean_anomaly, zones, n, "mean", groups)
    if min_vci is not None:
        out["min_vci"] = zonal_reduce(min_vci, zones, n, "min", groups)
    return out
