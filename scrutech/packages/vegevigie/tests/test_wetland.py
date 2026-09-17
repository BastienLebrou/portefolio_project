"""Wetland-potential tests — a flat basin scores wet, a steep slope does not."""

from __future__ import annotations

import numpy as np

from vegevigie.wetland import ndwi, topographic_wetness


def test_ndwi_water_is_positive() -> None:
    # Open water: green high, NIR low → NDWI > 0. Vegetation: NIR high → NDWI < 0.
    assert ndwi(np.array([0.3]), np.array([0.05]))[0] > 0
    assert ndwi(np.array([0.1]), np.array([0.5]))[0] < 0


def test_topographic_wetness_flags_the_flat_depression() -> None:
    # 40x40 DEM: a tilted plane (steep, dry) with a flat low basin carved in the middle.
    n = 40
    yy, xx = np.mgrid[0:n, 0:n]
    dem = (xx * 2.0).astype("float64")  # 2 m per pixel eastwards → a real slope everywhere
    dem[15:25, 15:25] = dem[15:25, 15:25].min() - 5.0  # a flat basin, 5 m below its surroundings

    wet = topographic_wetness(dem, cellsize=10.0)
    assert wet.shape == dem.shape
    assert (wet >= 0).all() and (wet <= 1).all()
    basin = wet[17:23, 17:23].mean()
    slope = wet[5:10, 5:10].mean()
    assert basin > slope  # the basin is wetter than the open slope
    assert basin > 0.3


def test_topographic_wetness_handles_nan() -> None:
    dem = np.full((20, 20), 100.0)
    dem[0, 0] = np.nan
    wet = topographic_wetness(dem, cellsize=10.0)
    assert np.isfinite(wet).all()  # NaN pixel → 0, no propagation
