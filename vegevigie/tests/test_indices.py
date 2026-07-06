"""SCL mask + NDVI tests — pure functions on synthetic arrays, no network (§8)."""

import numpy as np
import xarray as xr

from vegevigie.indices import (
    SCL_DROP_CLASSES,
    SCL_KEEP_CLASSES,
    apply_mask,
    compute_ndvi,
    masked_ndvi,
    scl_valid_mask,
)


def test_scl_keep_drop_partition_all_12_classes() -> None:
    # SCL defines classes 0..11; every one must be classified keep xor drop.
    all_classes = SCL_KEEP_CLASSES | SCL_DROP_CLASSES
    assert all_classes == set(range(12))
    assert SCL_KEEP_CLASSES.isdisjoint(SCL_DROP_CLASSES)


def test_scl_valid_mask_known_array() -> None:
    scl = np.array([0, 3, 4, 5, 6, 7, 8, 9, 10, 11])
    mask = scl_valid_mask(scl)
    # keep 4,5,6,7 -> positions 2..5 True, everything else False
    expected = np.array([False, False, True, True, True, True, False, False, False, False])
    assert np.array_equal(mask, expected)


def test_compute_ndvi_known_values() -> None:
    # NIR=0.6, Red=0.2 -> (0.6-0.2)/(0.6+0.2) = 0.5
    red = np.array([0.2, 0.5, 0.0])
    nir = np.array([0.6, 0.5, 0.0])  # last pixel: 0/0 -> NaN (guarded)
    ndvi = compute_ndvi(red, nir)
    assert np.isclose(ndvi[0], 0.5)
    assert np.isclose(ndvi[1], 0.0)
    assert np.isnan(ndvi[2])


def test_compute_ndvi_scale_invariant() -> None:
    # NDVI is a ratio: a common multiplicative scale must not change it.
    red = np.array([0.2, 0.3])
    nir = np.array([0.6, 0.4])
    assert np.allclose(compute_ndvi(red, nir), compute_ndvi(red * 10000, nir * 10000))


def test_apply_mask_blanks_invalid() -> None:
    data = np.array([0.5, 0.5, 0.5])
    valid = np.array([True, False, True])
    out = apply_mask(data, valid)
    assert np.array_equal(np.isnan(out), [False, True, False])


def test_masked_ndvi_end_to_end() -> None:
    red = np.array([0.2, 0.2, 0.2])
    nir = np.array([0.6, 0.6, 0.6])  # NDVI would be 0.5 everywhere
    scl = np.array([4, 9, 3])  # vegetation, cloud-high, cloud-shadow
    out = masked_ndvi(red, nir, scl)
    assert np.isclose(out[0], 0.5)  # kept
    assert np.isnan(out[1])  # cloud masked
    assert np.isnan(out[2])  # shadow masked


def test_masked_ndvi_preserves_xarray_labels() -> None:
    coords = {"y": [0, 1], "x": [0, 1]}
    red = xr.DataArray(np.full((2, 2), 0.2), dims=("y", "x"), coords=coords)
    nir = xr.DataArray(np.full((2, 2), 0.6), dims=("y", "x"), coords=coords)
    scl = xr.DataArray(np.array([[4, 9], [5, 3]]), dims=("y", "x"), coords=coords)
    out = masked_ndvi(red, nir, scl)
    assert isinstance(out, xr.DataArray)
    assert out.dims == ("y", "x")
    assert np.isclose(out.sel(y=0, x=0).item(), 0.5)  # vegetation kept
    assert np.isnan(out.sel(y=0, x=1).item())  # cloud masked
