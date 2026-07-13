"""Drought-stress detection from NDVI anomalies (CLAUDE.md §1.6).

A pixel is "under stress" when its vegetation is doing worse *than normal for the
time of year* — so we compare each monthly NDVI to that pixel's own history for
the same calendar month, not to a fixed threshold.

Concepts (teaching is a deliverable, §10):

- **Monthly climatology.** Per pixel, per calendar month (Jan…Dec), the mean /
  std / min / max NDVI across all years in the record. This is the pixel's
  "normal" seasonal envelope.
- **Anomaly (z-score).** ``(NDVI − climatology_mean) / climatology_std`` for that
  pixel-month. Negative ⇒ browner than usual; ≈ −1.5 or below is a notable dry
  stress signal. Being standardized, it's comparable across pixels and seasons.
- **VCI (Vegetation Condition Index).** ``100 · (NDVI − min) / (max − min)`` over
  the pixel-month history, in 0–100. 0 = worst month on record, 100 = best; low
  VCI (< ~35) is the classic drought flag. Complements the z-score (bounded, no
  std assumption).
- **Drought timeline.** The AOI-mean anomaly per month — a single curve that dips
  in dry years, for the dashboard.

All functions are pure, operate on the monthly NDVI ``DataArray`` (dims
time, y, x) with a datetime ``time`` axis, and vectorize over dask.
"""

from __future__ import annotations

import xarray as xr


def monthly_climatology(monthly: xr.DataArray, time_dim: str = "time") -> xr.Dataset:
    """Per-pixel, per-calendar-month NDVI mean/std/min/max across all years.

    Output dims are (month, y, x) with ``month`` in 1..12. Std uses ddof=0
    (population), the usual climatology convention.
    """
    grouped = monthly.groupby(f"{time_dim}.month")
    return xr.Dataset(
        {
            "clim_mean": grouped.mean(),
            "clim_std": grouped.std(),
            "clim_min": grouped.min(),
            "clim_max": grouped.max(),
        }
    )


def _climatology_for_each_step(
    field: xr.DataArray, monthly: xr.DataArray, time_dim: str
) -> xr.DataArray:
    """Broadcast a (month, y, x) climatology field back onto the time axis."""
    month_of_step = monthly[time_dim].dt.month
    return field.sel(month=month_of_step)


def ndvi_anomaly(
    monthly: xr.DataArray, climatology: xr.Dataset, time_dim: str = "time"
) -> xr.DataArray:
    """Standardized NDVI anomaly (z-score) vs the per-pixel monthly climatology.

    Pixels/months with zero climatological std (constant history) yield NaN.
    """
    mean = _climatology_for_each_step(climatology["clim_mean"], monthly, time_dim)
    std = _climatology_for_each_step(climatology["clim_std"], monthly, time_dim)
    z = (monthly - mean) / std
    return xr.where(std > 0, z, float("nan")).rename("ndvi_anomaly")


def vci(monthly: xr.DataArray, climatology: xr.Dataset, time_dim: str = "time") -> xr.DataArray:
    """Vegetation Condition Index in 0–100 vs the per-pixel monthly min/max.

    Flat-history pixels (max == min) yield NaN; otherwise clipped to [0, 100].
    """
    cmin = _climatology_for_each_step(climatology["clim_min"], monthly, time_dim)
    cmax = _climatology_for_each_step(climatology["clim_max"], monthly, time_dim)
    span = cmax - cmin
    v = 100.0 * (monthly - cmin) / span
    return xr.where(span > 0, v, float("nan")).clip(0.0, 100.0).rename("vci")


def drought_timeline(
    anomaly: xr.DataArray, spatial_dims: tuple[str, str] = ("y", "x")
) -> xr.DataArray:
    """AOI-mean anomaly per time step — the drought curve for the dashboard."""
    return anomaly.mean(dim=list(spatial_dims)).rename("anomaly_mean")


def drought_dataset(monthly: xr.DataArray, time_dim: str = "time") -> xr.Dataset:
    """Full M5 product: standardized anomaly + VCI stacked over (time, y, x)."""
    climatology = monthly_climatology(monthly, time_dim=time_dim)
    anomaly = ndvi_anomaly(monthly, climatology, time_dim=time_dim)
    condition = vci(monthly, climatology, time_dim=time_dim)
    return xr.Dataset({"ndvi_anomaly": anomaly, "vci": condition})
