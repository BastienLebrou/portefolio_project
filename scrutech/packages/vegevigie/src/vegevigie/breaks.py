"""When did the series break? — a per-pixel change-point (the practical BFAST-lite).

The trend answers *is it going up or down*; a **break** answers *when did it flip* — a clear-cut,
a fire, the onset of a drought. Full BFAST needs extra libraries; here we use **Pettitt's test**
(1979), a non-parametric single change-point detector: pure NumPy, robust to non-normal data,
and cheap enough to run per pixel over a datacube.

``pettitt_1d`` returns the break position, its p-value, and the direction of change (greening vs
browning break). :func:`break_dataset` vectorizes it over a monthly cube, like the trend stage.
"""

from __future__ import annotations

import numpy as np
import xarray as xr


def pettitt_1d(y: np.ndarray, min_valid: int = 8) -> tuple[float, float, float]:
    """Pettitt change-point on a 1-D series. Returns (break_index, p_value, direction).

    ``break_index`` is the position (in the full series) after which the distribution shifts;
    ``direction`` is +1 (upward/greening break), −1 (downward), 0 (undetermined). NaNs are
    ignored (they contribute 0 to the rank sums). Below ``min_valid`` points → all NaN.
    """
    y = np.asarray(y, dtype=float)
    n_valid = int(np.isfinite(y).sum())
    if n_valid < min_valid:
        return (np.nan, np.nan, 0.0)

    # y[:, None] transforme le vecteur 1D en colonne (n, 1), y[None, :] en ligne (1, n) ;
    # numpy les "broadcast" (étend automatiquement chaque forme pour matcher l'autre)
    # pour produire une matrice (n, n) de TOUTES les différences deux à deux d'un coup —
    # sans boucle explicite. C'est la même idée que triu_indices dans trend.py, mais ici
    # sous forme de matrice complète (utile pour ensuite sommer ligne par ligne).
    signs = np.sign(y[:, None] - y[None, :])  # (n, n); NaN pairs → NaN
    signs[~np.isfinite(signs)] = 0.0
    u = np.cumsum(signs.sum(axis=1))  # U_t, t = 0 … n-1
    k = int(np.argmax(np.abs(u)))
    k_stat = float(np.abs(u[k]))
    p_value = min(1.0, 2.0 * np.exp(-6.0 * k_stat**2 / (n_valid**3 + n_valid**2)))

    before, after = y[: k + 1], y[k + 1 :]
    mean_before = np.nanmean(before) if np.isfinite(before).any() else np.nan
    mean_after = np.nanmean(after) if np.isfinite(after).any() else np.nan
    direction = (
        float(np.sign(mean_after - mean_before))
        if np.isfinite(mean_after) and np.isfinite(mean_before)
        else 0.0
    )
    return (float(k), p_value, direction)


def break_dataset(monthly: xr.DataArray, min_valid: int = 8, time_dim: str = "time") -> xr.Dataset:
    """Per-pixel Pettitt break over the time axis. Lazy on a dask-backed cube.

    Returns ``break_index`` (position on the time axis), ``break_pvalue`` and
    ``break_direction`` (greening=+1 / browning=−1).
    """

    def _kernel(block: np.ndarray) -> tuple[float, float, float]:
        return pettitt_1d(block, min_valid=min_valid)

    # apply_ufunc needs the core dim (time) in a single chunk; the cube is chunked on time.
    if monthly.chunks is not None:
        monthly = monthly.chunk({time_dim: -1})

    index, pval, direction = xr.apply_ufunc(
        _kernel,
        monthly,
        input_core_dims=[[time_dim]],
        output_core_dims=[[], [], []],
        vectorize=True,
        dask="parallelized",
        output_dtypes=[float, float, float],
    )
    return xr.Dataset({"break_index": index, "break_pvalue": pval, "break_direction": direction})


def break_year(
    breaks: xr.Dataset, monthly: xr.DataArray, alpha: float = 0.05, time_dim: str = "time"
) -> xr.DataArray:
    """Map the break index to the calendar year, NaN where the break isn't significant.

    The headline "when did it change" layer: the year of the most likely break for pixels
    where Pettitt is significant at ``alpha``.
    """
    years = monthly[time_dim].dt.year.to_numpy()
    idx = breaks["break_index"].to_numpy()
    safe = np.clip(np.nan_to_num(idx, nan=0).astype(int), 0, len(years) - 1)
    year_grid = years[safe].astype(float)
    significant = breaks["break_pvalue"].to_numpy() < alpha
    year_grid[~significant | ~np.isfinite(idx)] = np.nan
    ref = breaks["break_index"]
    return xr.DataArray(year_grid, coords=ref.coords, dims=ref.dims)
