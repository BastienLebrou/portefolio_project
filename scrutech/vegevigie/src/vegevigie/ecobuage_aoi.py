"""AOI-only écobuage: derive every criterion from a study area + a DEM, then score.

The pure scoring engine (``ecobuage``) expects aligned criterion rasters. This orchestrator
BUILDS them from an emprise so the user supplies only a study area (+ a DEM path):

- **slope** ← the DEM (window over the AOI, slope in %, resampled to the analysis grid);
- **accessibility** ← distance to BD TOPO roads (fetched for the AOI via :mod:`core.sources`);
- **exclusions** ← BD TOPO buildings buffered (proximity to habitat);
- **combustible / embroussaillement** ← optional VegeVigie rasters (NDVI drought / trend) if
  given; otherwise those weights simply drop out of the weighted mean.

Everything lands on one L93 grid (``resolution`` m). Pure raster maths (numpy + rasterio +
scipy); the only network is the BD TOPO fetch. Outputs: aptitude (0-100) + 3-class GeoTIFFs.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

import numpy as np

logger = logging.getLogger("vegevigie")

L93 = "EPSG:2154"
_DEFAULT_WEIGHTS = {"combustible": 25.0, "embroussaillement": 25.0, "slope": 20.0, "access": 15.0}


def build_aptitude_from_aoi(
    aoi: object,
    mnt_path: str | Path,
    out_dir: Path,
    *,
    resolution: float = 25.0,
    veg_trend_tif: str | Path | None = None,
    veg_drought_tif: str | Path | None = None,
    exclusion_m: float = 100.0,
    access_max_m: float = 500.0,
    slope_lo: float = 15.0,
    slope_hi: float = 40.0,
    slope_ramp: float = 10.0,
    weights: dict[str, float] | None = None,
    progress=None,
) -> tuple[Path, Path, dict]:
    """Build écobuage aptitude + class rasters for the AOI. Returns (aptitude, classes, info)."""
    import ecobuage
    from core.aoi import resolve_aoi

    report = progress or (lambda _p, _m: None)
    weights = {**_DEFAULT_WEIGHTS, **(weights or {})}

    a = resolve_aoi(aoi)
    geom_l93 = a.to_l93()
    transform, width, height = _grid(geom_l93.bounds, resolution)
    logger.info("Écobuage grid: %dx%d @ %.0f m (L93).", width, height, resolution)

    report(20, "Slope from the DEM…")
    slope_pct = _slope_percent(Path(mnt_path), geom_l93.bounds, transform, width, height)

    report(45, "Accessibility from BD TOPO roads…")
    access = _access_from_roads(a, transform, width, height, access_max_m)

    report(65, "Exclusions from BD TOPO buildings…")
    exclusions = _exclusion_from_buildings(a, transform, width, height, exclusion_m)

    criteria: list[tuple[np.ndarray, float]] = [
        (ecobuage.band(slope_pct, slope_lo, slope_hi, slope_ramp), weights["slope"]),
        (access, weights["access"]),
    ]
    used = ["slope", "access"]
    embr = _read_to_grid(veg_trend_tif, transform, width, height)
    if embr is not None:  # positive NDVI trend on parcours = ligneous recolonisation
        criteria.append((ecobuage.rescale(embr, 0.0, 0.01), weights["embroussaillement"]))
        used.append("embroussaillement")
    drought = _read_to_grid(veg_drought_tif, transform, width, height)
    if drought is not None:  # more negative NDVI anomaly = drier senescent biomass = combustible
        criteria.append((ecobuage.rescale(drought, 0.0, -2.0), weights["combustible"]))
        used.append("combustible")

    report(80, "Weighted scoring…")
    score = ecobuage.aptitude(criteria, exclusions=exclusions)
    classes = ecobuage.classify(score)

    out_dir.mkdir(parents=True, exist_ok=True)
    apt_path = out_dir / "ecobuage_aptitude.tif"
    cls_path = out_dir / "ecobuage_classes.tif"
    profile = {
        "driver": "GTiff",
        "crs": L93,
        "transform": transform,
        "width": width,
        "height": height,
    }
    _write_tif(apt_path, score.astype("float32"), profile)
    _write_tif(cls_path, classes.astype("uint8"), profile)

    info = {
        "criteria": used,
        "n_prioritaire": int((classes == 2).sum()),
        "n_a_etudier": int((classes == 1).sum()),
        "n_a_exclure": int((classes == 0).sum()),
        "grid": [width, height, resolution],
    }
    report(100, f"Aptitude: {info['n_prioritaire']} px prioritaires, criteria={used}.")
    logger.info("Écobuage AOI: %s", info)
    return apt_path, cls_path, info


# --- grid + criterion builders ------------------------------------------------
def _grid(bounds: tuple, resolution: float):
    """Target L93 grid (Affine transform, width, height) covering ``bounds`` at ``resolution``."""
    from rasterio.transform import from_origin

    minx, miny, maxx, maxy = bounds
    width = max(1, int(math.ceil((maxx - minx) / resolution)))
    height = max(1, int(math.ceil((maxy - miny) / resolution)))
    return from_origin(minx, maxy, resolution, resolution), width, height


def _slope_percent(mnt_path: Path, bounds: tuple, transform, width: int, height: int) -> np.ndarray:
    """Read the DEM window over the AOI, compute slope (%), resample to the target grid.

    The DEM CRS tag may be missing; it is assumed to be Lambert-93 (its coordinates are).
    """
    import rasterio
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import from_bounds

    minx, miny, maxx, maxy = bounds
    with rasterio.open(mnt_path) as ds:
        pad = 200.0  # metres of margin so edge gradients are valid
        win = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad, ds.transform)
        arr = ds.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        win_transform = ds.window_transform(win)
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan
        cell = abs(ds.transform.a)

    gy, gx = np.gradient(arr, cell)
    slope_pct = np.hypot(gx, gy) * 100.0
    slope_pct = np.nan_to_num(slope_pct, nan=0.0)

    dest = np.zeros((height, width), dtype="float64")
    reproject(
        source=slope_pct,
        destination=dest,
        src_transform=win_transform,
        src_crs=L93,
        dst_transform=transform,
        dst_crs=L93,
        resampling=Resampling.bilinear,
    )
    return dest


def _access_from_roads(aoi, transform, width: int, height: int, access_max_m: float) -> np.ndarray:
    """Rasterize BD TOPO roads, distance-transform to metres, rescale (0 m = 1, ≥ max = 0)."""
    from core.sources import fetch_roads

    roads = fetch_roads(aoi)
    road_mask = _rasterize(roads, transform, width, height)
    if not road_mask.any():
        logger.warning("No roads in the AOI — accessibility set to 0 everywhere.")
        return np.zeros((height, width), dtype="float64")

    from scipy.ndimage import distance_transform_edt

    cell = abs(transform.a)
    dist_m = distance_transform_edt(~road_mask) * cell
    return np.clip(1.0 - dist_m / access_max_m, 0.0, 1.0)


def _exclusion_from_buildings(
    aoi, transform, width: int, height: int, exclusion_m: float
) -> np.ndarray:
    """Boolean mask of cells within ``exclusion_m`` of a BD TOPO building."""
    from core.sources import fetch_buildings

    bati = fetch_buildings(aoi)
    if bati.empty:
        return np.zeros((height, width), dtype=bool)
    buffered = bati.copy()
    buffered["geometry"] = bati.buffer(exclusion_m)
    return _rasterize(buffered, transform, width, height)


def _rasterize(gdf, transform, width: int, height: int) -> np.ndarray:
    """Burn a (L93) GeoDataFrame onto the grid → boolean presence mask."""
    from rasterio.features import rasterize

    if gdf is None or gdf.empty:
        return np.zeros((height, width), dtype=bool)
    shapes = ((geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty)
    burned = rasterize(
        shapes, out_shape=(height, width), transform=transform, fill=0, dtype="uint8"
    )
    return burned.astype(bool)


def _read_to_grid(tif: str | Path | None, transform, width: int, height: int) -> np.ndarray | None:
    """Reproject an optional VegeVigie raster onto the target grid (None if not provided)."""
    if tif is None:
        return None
    import rasterio
    from rasterio.warp import Resampling, reproject

    dest = np.full((height, width), np.nan, dtype="float64")
    with rasterio.open(tif) as ds:
        reproject(
            source=ds.read(1).astype("float64"),
            destination=dest,
            src_transform=ds.transform,
            src_crs=ds.crs or L93,
            dst_transform=transform,
            dst_crs=L93,
            resampling=Resampling.bilinear,
        )
    return np.nan_to_num(dest, nan=0.0)


def _write_tif(path: Path, arr: np.ndarray, profile: dict) -> None:
    import rasterio

    prof = {**profile, "count": 1, "dtype": arr.dtype.name}
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(arr, 1)
