"""AOI helpers for the vegevigie pipeline.

Thin façade over :mod:`core.aoi` for commune boundaries — now every French
département via geo.api.gouv.fr (was Ardèche-only, fixes B3) — plus the
pipeline-specific bbox clip / dissolve / GeoParquet layer builder used by the
``aoi`` CLI stage.

``fetch_communes`` is re-exported from core; tests still monkeypatch
``vegevigie.aoi.fetch_communes`` and :func:`build_aoi` picks that up via the module
global. Everything is WGS84 (EPSG:4326); reprojection happens in the datacube stage.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
from core.aoi import WGS84, BBox, fetch_communes
from shapely.geometry import box

logger = logging.getLogger("vegevigie")

__all__ = ["WGS84", "BBox", "fetch_communes", "clip_to_bbox", "dissolve_boundary", "build_aoi"]


def clip_to_bbox(communes: gpd.GeoDataFrame, bbox: BBox) -> gpd.GeoDataFrame:
    """Return the communes intersecting ``bbox`` (min_lon, min_lat, max_lon, max_lat).

    Pure geometry op — kept whole-commune (not cut) so downstream zonal stats stay
    meaningful; a commune is included if it overlaps the bbox at all.
    """
    aoi_geom = box(*bbox)
    selected = communes[communes.intersects(aoi_geom)].copy()
    logger.info("Clipped to bbox %s: %d/%d communes overlap", bbox, len(selected), len(communes))
    return selected


def dissolve_boundary(communes: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    """Dissolve commune polygons into a single AOI outline (pure)."""
    merged = communes.union_all()
    return gpd.GeoDataFrame({"name": [name]}, geometry=[merged], crs=communes.crs)


def build_aoi(
    dept: str,
    name: str,
    raw_dir: Path,
    small_bbox: BBox | None = None,
    force: bool = False,
) -> tuple[Path, Path]:
    """Build the commune and AOI GeoParquet layers; return their paths.

    ``small_bbox`` set  -> AOI = communes overlapping that bbox (smoke run).
    ``small_bbox`` None -> AOI = whole-département outline.
    Idempotent: skips the download if both outputs already exist unless ``force``.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    communes_path = raw_dir / f"communes_{dept}.parquet"
    aoi_path = raw_dir / "aoi.parquet"

    if not force and communes_path.exists() and aoi_path.exists():
        logger.info("AOI outputs already present; use --force to rebuild. Skipping.")
        return communes_path, aoi_path

    communes = fetch_communes(dept)
    communes.to_parquet(communes_path)

    if small_bbox is not None:
        clip_to_bbox(communes, small_bbox).to_parquet(aoi_path)
    else:
        dissolve_boundary(communes, name).to_parquet(aoi_path)

    logger.info("Wrote %s and %s", communes_path, aoi_path)
    return communes_path, aoi_path
