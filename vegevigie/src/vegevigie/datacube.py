"""Build a lazy Sentinel-2 datacube from cached STAC items.

**Datacube** = the scene stack reshaped into one N-dimensional array indexed by
(time, y, x), one variable per band. We load only three bands — Red (B04),
NIR (B08) and SCL — because that's all NDVI + cloud masking need.

Concepts introduced here (CLAUDE.md §10 — teaching is a deliverable):

- **COG (Cloud-Optimized GeoTIFF).** Each Sentinel-2 asset is a GeoTIFF laid out
  so a reader can fetch just the pixels/overviews it needs over HTTP. That's what
  lets us pull a small AOI at coarse resolution without downloading whole tiles.
- **Lazy / dask.** ``odc.stac.load(..., chunks=...)`` returns an xarray Dataset
  backed by dask: nothing is downloaded yet, only a task graph. Compute happens
  when we ``.compute()`` / write to zarr. This keeps a multi-year cube tractable.
- **UTM grid.** Sentinel-2 tiles are projected per UTM zone. We let odc-stac pick
  the native UTM CRS from the items (Ardèche sits in a single zone, EPSG:32631) so
  no cross-zone resampling is needed; resolution is set in metres.
- **BOA offset.** Since processing baseline 04.00, L2A reflectance carries an
  additive −1000 offset (scale 1/10000). NDVI is a ratio, so the scale cancels but
  the *offset* does not — we apply it here so ``indices.compute_ndvi`` receives
  true surface reflectance.
- **Signing.** Planetary Computer asset hrefs expire; every item is re-signed just
  before loading (never cached signed).

Loading needs network access to ``planetarycomputer.microsoft.com``; the CLI
reports a blocked host cleanly when the egress policy denies it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from vegevigie.catalog import StacBackend

if TYPE_CHECKING:
    import xarray as xr

logger = logging.getLogger("vegevigie")

# Asset key (Sentinel-2 band) -> friendly cube variable name.
BAND_ALIASES: dict[str, str] = {"B04": "red", "B08": "nir", "SCL": "scl"}

# Sentinel-2 L2A harmonization (processing baseline >= 04.00).
BOA_SCALE = 1.0 / 10000.0
BOA_OFFSET = -1000.0  # applied in DN space before scaling

BBox = tuple[float, float, float, float]


def _sign_items(backend: StacBackend, item_dicts: list[dict[str, Any]]) -> list[Any]:
    """Convert cached item dicts to signed pystac Items ready for odc.stac.load."""
    import pystac

    signed = []
    for d in item_dicts:
        item = pystac.Item.from_dict(d)
        signed.append(backend.sign(item))
    logger.info("Signed %d STAC items", len(signed))
    return signed


def harmonize_reflectance(cube: xr.Dataset) -> xr.Dataset:
    """Apply the Sentinel-2 BOA offset+scale to Red/NIR; leave SCL (a class code) as-is.

    Pure transform on an xarray Dataset — kept separate so it's unit-testable and so
    the harmonization convention is explicit rather than hidden in load kwargs.
    """
    out = cube.copy()
    for band in ("red", "nir"):
        if band in out:
            out[band] = (out[band] + BOA_OFFSET) * BOA_SCALE
    return out


def build_cube(
    backend: StacBackend,
    item_dicts: list[dict[str, Any]],
    bbox: BBox,
    resolution: int,
    chunk_size: int,
) -> xr.Dataset:
    """Load a lazy (Red, NIR, SCL) datacube over ``bbox`` at ``resolution`` metres.

    Groups observations by solar day, clips to the AOI bbox, and returns a
    dask-backed Dataset with harmonized reflectance. No pixels are fetched until
    the result is computed or written.
    """
    import odc.stac

    signed = _sign_items(backend, item_dicts)
    logger.info(
        "Loading datacube: %d items, res=%dm, chunk=%d, bbox=%s",
        len(signed),
        resolution,
        chunk_size,
        tuple(round(c, 3) for c in bbox),
    )
    cube = odc.stac.load(
        signed,
        bands=list(BAND_ALIASES),
        bbox=bbox,
        resolution=resolution,
        chunks={"x": chunk_size, "y": chunk_size},
        groupby="solar_day",
    ).rename(BAND_ALIASES)
    return harmonize_reflectance(cube)


def write_zarr(cube: xr.Dataset, path: Path, force: bool = False) -> Path:
    """Persist the datacube to zarr (idempotent unless ``force``)."""
    if path.exists() and not force:
        logger.info("Datacube already cached at %s (use --force to rebuild)", path)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    mode: Literal["w", "w-"] = "w" if force else "w-"
    cube.to_zarr(path, mode=mode)
    logger.info("Wrote datacube to %s", path)
    return path


def open_zarr(path: Path) -> xr.Dataset:
    """Open a cached datacube written by :func:`write_zarr` (lazy).

    ``decode_coords="all"`` re-attaches CF grid-mapping variables (``spatial_ref``)
    as coordinates, so ``.rio.crs`` survives the zarr round-trip regardless of
    whether the writer recorded the CRS via attrs or encoding.
    """
    import xarray as xr

    return xr.open_zarr(path, decode_coords="all")
