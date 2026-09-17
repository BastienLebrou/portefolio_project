"""Pettitt break-detection tests — a clear step is found, flat noise is not."""

from __future__ import annotations

import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.breaks import break_dataset, break_year, pettitt_1d


def test_pettitt_finds_a_step_change() -> None:
    # 12 low then 12 high → break around index 11, upward direction, significant.
    y = (
        np.concatenate([np.full(12, 0.2), np.full(12, 0.7)])
        + np.random.RandomState(0).randn(24) * 0.01
    )
    k, p, direction = pettitt_1d(y)
    assert 9 <= k <= 13
    assert p < 0.05
    assert direction == 1.0


def test_pettitt_flat_noise_is_not_significant() -> None:
    y = np.random.RandomState(1).randn(30) * 0.02 + 0.5
    _k, p, _d = pettitt_1d(y)
    assert p > 0.05


def test_pettitt_insufficient_data_is_nan() -> None:
    k, p, _d = pettitt_1d(np.array([0.1, 0.2, np.nan, 0.3]))
    assert np.isnan(k) and np.isnan(p)


def test_break_dataset_and_year_on_time_chunked_cube() -> None:
    t = pd.date_range("2018-01-01", periods=24, freq="MS")
    step = np.concatenate([np.full(12, 0.2), np.full(12, 0.7)])
    # broadcast_to répète le vecteur `step` sur les 2×2 pixels SANS dupliquer la mémoire
    # (une "vue" partagée) ; .copy() en fait ensuite un vrai tableau indépendant, car un
    # DataArray xarray a besoin de pouvoir être modifié/chunké normalement (une vue
    # broadcastée ne le permet pas toujours).
    data = np.broadcast_to(step[:, None, None], (24, 2, 2)).copy()
    da = xr.DataArray(data, dims=("time", "y", "x"), coords={"time": t}).chunk({"time": 6})

    ds = break_dataset(da)
    computed = ds.compute()
    assert set(computed.data_vars) == {"break_index", "break_pvalue", "break_direction"}
    assert computed["break_index"].shape == (2, 2)

    yr = break_year(computed, da)
    # The break sits at the 2018→2019 boundary; significant pixels get year 2019.
    assert set(np.unique(yr.to_numpy()[np.isfinite(yr.to_numpy())])) <= {2018.0, 2019.0}
