"""Cloud masking and NDVI — the pure science of the pixel-value pipeline.

Two operations, both pure (no I/O), so they unit-test on tiny synthetic arrays
(CLAUDE.md §7/§8) and vectorize cleanly over an xarray/dask datacube.

**SCL (Scene Classification Layer)** is a per-pixel classification band shipped
with every Sentinel-2 L2A scene (20 m native): each pixel is labelled vegetation,
bare soil, water, cloud, shadow, snow, etc. We use it as a quality mask — keep the
land/water classes, drop everything cloud/shadow/snow/defective — so downstream
NDVI and trends aren't polluted by clouds.

**NDVI** (Normalized Difference Vegetation Index) = (NIR − Red) / (NIR + Red),
from Sentinel-2 B08 (NIR) and B04 (Red), both native 10 m. Ranges roughly −1
(water/cloud) to +1 (dense vegetation); healthy canopy sits ~0.6–0.9. NDVI is a
*ratio*, so a common multiplicative reflectance scale cancels — but an additive
offset does not, so callers must pass harmonized surface reflectance (see
:mod:`vegevigie.datacube`, which applies the Sentinel-2 BOA offset at load time).
"""

from __future__ import annotations

from typing import Any, TypeVar

import numpy as np

# SCL class codes (Sentinel-2 L2A). Keep land/water/unclassified; drop the rest.
# Values are a hard part of the sensor spec — hard-coded and commented per §5.
SCL_KEEP_CLASSES: frozenset[int] = frozenset(
    {
        4,  # vegetation
        5,  # bare soils
        6,  # water
        7,  # unclassified
    }
)
SCL_DROP_CLASSES: frozenset[int] = frozenset(
    {
        0,  # no data
        1,  # saturated / defective
        2,  # dark area / topographic shadow
        3,  # cloud shadow
        8,  # cloud, medium probability
        9,  # cloud, high probability
        10,  # thin cirrus
        11,  # snow / ice
    }
)

# Works for numpy arrays and xarray DataArrays alike. The dispatch helpers below
# keep xarray labels/coords (and dask laziness) intact — plain np.where / np.isin
# would silently drop them and return a bare ndarray.
ArrayT = TypeVar("ArrayT")


def _is_xarray(obj: object) -> bool:
    return type(obj).__module__.startswith("xarray")


def _where(cond: Any, a: Any, b: Any) -> Any:
    if _is_xarray(cond) or _is_xarray(a) or _is_xarray(b):
        import xarray as xr

        return xr.where(cond, a, b)
    return np.where(cond, a, b)


def _as_float(x: Any) -> Any:
    return x.astype("float64") if _is_xarray(x) else np.asarray(x, dtype="float64")


def scl_valid_mask(scl: ArrayT) -> ArrayT:
    """Boolean mask: True where the SCL class is a *keep* class (clear land/water).

    Membership in :data:`SCL_KEEP_CLASSES` — the complement of the
    cloud/shadow/snow/defective classes we discard.
    """
    keep = sorted(SCL_KEEP_CLASSES)
    if _is_xarray(scl):
        return scl.isin(keep)  # type: ignore[attr-defined]
    return np.isin(np.asarray(scl), keep)  # type: ignore[return-value]


def apply_mask(data: ArrayT, valid: ArrayT) -> ArrayT:
    """Set invalid (masked-out) pixels to NaN, leaving valid pixels untouched.

    Result is float so NaN can be stored (reflectance/NDVI are floats anyway).
    """
    return _where(valid, data, np.nan)


def compute_ndvi(red: ArrayT, nir: ArrayT) -> ArrayT:
    """NDVI = (NIR − Red) / (NIR + Red).

    Guards the divide-by-zero at (NIR + Red)==0 (e.g. nodata/black pixels) by
    emitting NaN there instead of an inf/warning.
    """
    red_f = _as_float(red)
    nir_f = _as_float(nir)
    denom = nir_f + red_f
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = (nir_f - red_f) / denom
    return _where(denom == 0, np.nan, ndvi)


def masked_ndvi(red: ArrayT, nir: ArrayT, scl: ArrayT) -> ArrayT:
    """Compute NDVI and blank out cloud/shadow/snow pixels using the SCL mask."""
    ndvi = compute_ndvi(red, nir)
    return apply_mask(ndvi, scl_valid_mask(scl))
