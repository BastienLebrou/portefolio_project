"""Monthly median NDVI composites — turning irregular scenes into a clean grid.

**Temporal compositing.** Sentinel-2 revisits every ~5 days, but after cloud
masking the *usable* observations per pixel are irregular and sparse. Before any
trend test we collapse them onto a regular monthly grid: for each pixel and each
calendar month, take the **median** of that month's valid (unmasked) NDVI values.
The median is robust to the odd residual haze/cloud edge the SCL mask missed, and
a regular monthly step is what the per-pixel Mann-Kendall/Sen stage (M4) expects.

**Gap-aware.** A month with *no* valid observation for a pixel must stay ``NaN`` —
a real gap — not be filled with zero or a neighbour. :func:`monthly_median` does
exactly that (median of an all-NaN slice is NaN). :func:`fill_temporal_gaps` can
optionally interpolate *short* gaps (up to ``max_gap`` months) along time, leaving
longer gaps as NaN so we never invent a season we didn't observe.

All functions are pure and operate on an ``xarray.DataArray`` with a datetime
``time`` axis, so they vectorize over a dask-backed cube and unit-test on tiny
synthetic arrays offline.
"""

from __future__ import annotations

import xarray as xr

# Month-start frequency: one composite per calendar month, labelled on the 1st.
MONTH_FREQ = "MS"


def monthly_median(ndvi: xr.DataArray, time_dim: str = "time") -> xr.DataArray:
    """Median NDVI per calendar month (gap-aware).

    Resamples the time axis to month-start and takes the per-pixel median, skipping
    NaNs. Months with no valid observation come out as NaN.
    """
    composite = ndvi.resample({time_dim: MONTH_FREQ}).median(skipna=True)
    return composite.rename("ndvi_monthly")


def valid_count_per_month(ndvi: xr.DataArray, time_dim: str = "time") -> xr.DataArray:
    """Number of valid (non-NaN) observations feeding each monthly composite.

    Useful as a confidence/diagnostic layer: a composite backed by one hazy scene
    is weaker than one backed by five clear ones.
    """
    count = ndvi.notnull().resample({time_dim: MONTH_FREQ}).sum()
    return count.rename("valid_count")


def fill_temporal_gaps(
    monthly: xr.DataArray, max_gap: int = 1, time_dim: str = "time"
) -> xr.DataArray:
    """Linearly interpolate gaps of at most ``max_gap`` consecutive months along time.

    Longer gaps and leading/trailing gaps (no bracketing values to interpolate
    between) are left as NaN — we fill only what we can defensibly reconstruct.
    ``max_gap=0`` returns the input unchanged.
    """
    if max_gap <= 0:
        return monthly
    # interpolate_na measures a gap as the distance between the valid points that
    # bracket a NaN run, i.e. (n_missing_months + 1). To fill runs of up to
    # `max_gap` missing months we therefore allow a bracketing distance of
    # max_gap + 1. use_coordinate=False treats the monthly grid as equidistant, so
    # a filled month lands on the straight-line midpoint regardless of month length.
    filled = monthly.interpolate_na(
        dim=time_dim, method="linear", use_coordinate=False, max_gap=max_gap + 1
    )
    return filled.rename(monthly.name)


def build_monthly_ndvi(
    ndvi: xr.DataArray, fill_max_gap: int = 0, time_dim: str = "time"
) -> xr.DataArray:
    """Full M3 composite: monthly median, optionally short-gap-filled."""
    composite = monthly_median(ndvi, time_dim=time_dim)
    if fill_max_gap > 0:
        composite = fill_temporal_gaps(composite, max_gap=fill_max_gap, time_dim=time_dim)
    return composite
