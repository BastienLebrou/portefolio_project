"""Per-pixel trend detection — the project headline (CLAUDE.md §5).

Two classic non-parametric statistics, ported to a vectorized, NaN-aware kernel
that runs blockwise over a dask-backed datacube instead of looping a library over
millions of pixels:

- **Mann-Kendall (MK)** — tests for a *monotonic* trend without assuming a
  distribution. It sums the sign of every pairwise change (the S statistic),
  standardizes it to a z-score with a tie-corrected variance, and turns that into
  a two-sided p-value. Direction + significance: *is this pixel greening or
  browning, and is it real?*
- **Theil–Sen slope** — the robust trend *magnitude*: the median of all pairwise
  slopes (yⱼ−yᵢ)/(j−i). Median-based, so a few outlier months barely move it.
  *How fast?*

This kernel is validated to match ``pymannkendall.original_test`` /
``sens_slope`` (see tests), reproducing its exact conventions:

- MK score/variance/z/p are computed on the NaN-*skipped* series (indices
  collapsed), matching pymannkendall's ``method='skip'``.
- The Sen slope uses the *original* month positions (gaps preserved via the true
  j−i denominator), with NaN pairs dropped by ``nanmedian``.

Because it's pure NumPy over the time axis, :func:`trend_dataset` wraps it with
``xr.apply_ufunc(..., dask="parallelized")`` so a department-scale cube is
processed chunk by chunk.
"""

from __future__ import annotations

import numpy as np
import xarray as xr
from scipy.stats import norm

# trend_class integer codes.
BROWNING = -1
NO_TREND = 0
GREENING = 1


def _mk_variance(values: np.ndarray, n: int) -> float:
    """Tie-corrected variance of the MK S statistic (matches pymannkendall)."""
    unique, counts = np.unique(values, return_counts=True)
    if len(unique) == n:  # no ties
        return (n * (n - 1) * (2 * n + 5)) / 18.0
    tie = counts
    return (n * (n - 1) * (2 * n + 5) - np.sum(tie * (tie - 1) * (2 * tie + 5))) / 18.0


def mk_sen_1d(
    y: np.ndarray, alpha: float = 0.05, min_valid: int = 4
) -> tuple[float, float, float, float]:
    """Mann-Kendall + Theil-Sen for one time series.

    Returns ``(sen_slope, mk_pvalue, mk_z, trend_class)``. Pixels with fewer than
    ``min_valid`` valid observations return all-NaN.
    """
    y = np.asarray(y, dtype="float64")
    n = y.size
    valid = ~np.isnan(y)
    m = int(valid.sum())
    if m < min_valid:
        return (np.nan, np.nan, np.nan, np.nan)

    # --- MK on the NaN-skipped series (indices collapsed) ---
    yv = y[valid]
    iu, ju = np.triu_indices(m, k=1)
    s = float(np.sum(np.sign(yv[ju] - yv[iu])))
    var_s = _mk_variance(yv, m)

    if var_s <= 0:
        z = 0.0
    elif s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0
    p = float(2 * norm.sf(abs(z)))

    # --- Theil-Sen slope on original positions (gaps preserved) ---
    oi, oj = np.triu_indices(n, k=1)
    slopes = (y[oj] - y[oi]) / (oj - oi)
    slope = float(np.nanmedian(slopes)) if np.isfinite(slopes).any() else np.nan

    significant = p < alpha
    if significant and z > 0:
        trend_class = float(GREENING)
    elif significant and z < 0:
        trend_class = float(BROWNING)
    else:
        trend_class = float(NO_TREND)

    return (slope, p, z, trend_class)


def trend_dataset(
    monthly: xr.DataArray,
    alpha: float = 0.05,
    min_valid: int = 6,
    time_dim: str = "time",
) -> xr.Dataset:
    """Apply :func:`mk_sen_1d` per pixel over the time axis.

    Returns a Dataset with ``sen_slope`` (NDVI units per month), ``mk_pvalue``,
    ``mk_z`` and ``trend_class`` (greening=1 / no-trend=0 / browning=-1). Lazy when
    the input is dask-backed.
    """

    def _kernel(block: np.ndarray) -> tuple[float, float, float, float]:
        return mk_sen_1d(block, alpha=alpha, min_valid=min_valid)

    slope, pval, zscore, tclass = xr.apply_ufunc(
        _kernel,
        monthly,
        input_core_dims=[[time_dim]],
        output_core_dims=[[], [], [], []],
        vectorize=True,
        dask="parallelized",
        output_dtypes=[float, float, float, float],
    )
    return xr.Dataset(
        {
            "sen_slope": slope,
            "mk_pvalue": pval,
            "mk_z": zscore,
            "trend_class": tclass,
        }
    )
