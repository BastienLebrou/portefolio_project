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
    # PÉDAGOGIE — ce que fait ce noyau, en clair : sur la série NDVI d'UN pixel (une valeur
    # par mois), on répond à « ça monte ou ça descend, est-ce significatif, et à quelle vitesse ».
    y = np.asarray(y, dtype="float64")

    # 1) On repère les mois RÉELLEMENT observés (un nuage/gap = NaN). `valid_idx` garde leur
    #    position d'origine sur l'axe du temps (essentiel pour la vitesse, plus bas).
    valid_idx = np.flatnonzero(~np.isnan(y))
    m = valid_idx.size
    if m < min_valid:
        # Trop peu d'observations → on refuse de conclure (tout NaN), plutôt que de bluffer.
        return (np.nan, np.nan, np.nan, np.nan)

    # 2) On compare CHAQUE mois à chaque autre mois (toutes les paires i<j), une seule fois.
    #    `triu_indices` = les indices du triangle supérieur d'une matrice m×m → toutes les paires.
    #    `diffs` = la variation de NDVI entre les deux mois de chaque paire. Ces paires servent
    #    aux DEUX statistiques ci-dessous.
    yv = y[valid_idx]
    iu, ju = np.triu_indices(m, k=1)
    diffs = yv[ju] - yv[iu]

    # 3) MANN-KENDALL — « ça monte ou ça descend ? ». On ne regarde QUE le signe de chaque
    #    variation (+1 si ça a monté, −1 si ça a baissé, 0 si égal). La somme S de ces signes
    #    est très positive si la série grimpe globalement, très négative si elle chute.
    s = float(np.sum(np.sign(diffs)))
    var_s = _mk_variance(yv, m)  # dispersion attendue de S sous l'hypothèse « pas de tendance »

    # On standardise S en un score z (nb d'écarts-types à zéro). La « −1 / +1 » est la
    # correction de continuité de Kendall (rapproche S de 0 d'un cran avant de diviser).
    if var_s <= 0:
        z = 0.0
    elif s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0
    # p-value bilatérale : probabilité d'observer un z aussi extrême par pur hasard.
    # Petit p (< alpha) = la tendance est significative, pas un artefact.
    p = float(2 * norm.sf(abs(z)))

    # 4) PENTE DE THEIL-SEN — « à quelle vitesse ? ». Pour chaque paire, la pente = variation
    #    de NDVI / nombre de mois écoulés (on utilise les positions D'ORIGINE, donc les trous
    #    comptent). La MÉDIANE de toutes ces pentes est la tendance robuste : quelques mois
    #    aberrants ne la déplacent quasiment pas (contrairement à une moyenne).
    slope = float(np.median(diffs / (valid_idx[ju] - valid_idx[iu])))

    # 5) VERDICT — on ne classe « verdissement » / « brunissement » que si c'est significatif ;
    #    sinon « pas de tendance » (on ne sur-interprète pas le bruit).
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

    # apply_ufunc needs the core dim (time) in a single dask chunk; the datacube
    # is chunked along time, so collapse it first (dask path only).
    if monthly.chunks is not None:
        monthly = monthly.chunk({time_dim: -1})

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
