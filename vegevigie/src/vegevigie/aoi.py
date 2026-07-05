"""Area-of-interest construction from official French admin boundaries.

This stage turns administrative boundaries into two GeoParquet layers under
``data/raw``:

- ``communes_<dept>.parquet`` — every commune polygon of the département (reused
  later for zonal aggregation, CLAUDE.md §M6);
- ``aoi.parquet`` — the analysis footprint: either the whole département outline
  (``--full``) or the communes clipped to the smoke-test bbox (``--small``).

Boundary source note: the canonical sources (``geo.api.gouv.fr``, IGN
``data.geopf.fr``) are unreachable from the CI/web egress policy used here, so we
read the community ``france-geojson`` mirror (derived from official IGN
ADMIN-EXPRESS data) over ``raw.githubusercontent.com``. The download lives behind
:func:`fetch_communes` so swapping back to the official API later is a one-function
change; the geometry maths below are pure and source-agnostic.

Everything is WGS84 (EPSG:4326) here — reprojection to the Sentinel-2 UTM grid
happens in the datacube stage (M2), not in the vector layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import box

logger = logging.getLogger("vegevigie")

WGS84 = "EPSG:4326"

# France-geojson mirror: one GeoJSON of commune polygons per département.
# Path pattern: departements/<dd>-<slug>/communes-<dd>-<slug>.geojson
_FRANCE_GEOJSON_BASE = (
    "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements"
)

# département code -> url slug (extend as new départements are needed).
_DEPT_SLUGS = {
    "07": "07-ardeche",
}

BBox = tuple[float, float, float, float]


def _communes_url(dept: str) -> str:
    try:
        slug = _DEPT_SLUGS[dept]
    except KeyError as exc:
        known = ", ".join(sorted(_DEPT_SLUGS))
        msg = f"No boundary URL slug registered for département {dept!r} (known: {known})"
        raise KeyError(msg) from exc
    return f"{_FRANCE_GEOJSON_BASE}/{slug}/communes-{slug}.geojson"


def fetch_communes(dept: str, timeout: int = 60) -> gpd.GeoDataFrame:
    """Download the commune polygons of a département as a WGS84 GeoDataFrame.

    Columns: ``code`` (INSEE), ``nom``, ``geometry``. This is the only network I/O
    in the AOI stage.
    """
    url = _communes_url(dept)
    logger.info("Fetching commune boundaries for dept %s from %s", dept, url)
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    gdf = gpd.GeoDataFrame.from_features(resp.json()["features"], crs=WGS84)
    logger.info("Loaded %d communes for dept %s", len(gdf), dept)
    return gdf[["code", "nom", "geometry"]]


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
        aoi = clip_to_bbox(communes, small_bbox)
        aoi.to_parquet(aoi_path)
    else:
        dissolve_boundary(communes, name).to_parquet(aoi_path)

    logger.info("Wrote %s and %s", communes_path, aoi_path)
    return communes_path, aoi_path
