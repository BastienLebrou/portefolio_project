"""Datacube pure-transform tests (harmonization) — no network."""

import numpy as np
import xarray as xr

from vegevigie.datacube import BOA_OFFSET, BOA_SCALE, harmonize_reflectance


def _synthetic_cube() -> xr.Dataset:
    return xr.Dataset(
        {
            "red": (("y", "x"), np.array([[1200, 2200], [3200, 4200]], dtype="int32")),
            "nir": (("y", "x"), np.array([[5200, 6200], [7200, 8200]], dtype="int32")),
            "scl": (("y", "x"), np.array([[4, 9], [5, 3]], dtype="uint8")),
        }
    )


def test_harmonize_applies_offset_and_scale_to_reflectance() -> None:
    out = harmonize_reflectance(_synthetic_cube())
    # DN 1200 -> (1200 - 1000) / 10000 = 0.02
    assert np.isclose(out["red"].values[0, 0], (1200 + BOA_OFFSET) * BOA_SCALE)
    assert np.isclose(out["nir"].values[0, 0], (5200 + BOA_OFFSET) * BOA_SCALE)


def test_harmonize_leaves_scl_untouched() -> None:
    cube = _synthetic_cube()
    out = harmonize_reflectance(cube)
    assert np.array_equal(out["scl"].values, cube["scl"].values)


def test_harmonize_does_not_mutate_input() -> None:
    cube = _synthetic_cube()
    before = cube["red"].values.copy()
    harmonize_reflectance(cube)
    assert np.array_equal(cube["red"].values, before)
