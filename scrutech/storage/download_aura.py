"""Download the ScruTech region-scale cache for Auvergne-Rhône-Alpes (AURA).

Covers the 💾 SIG needs of the pillars **except** built-up zones (OCS GE), BD Forêt and
slopes (DEM) — those are handled separately. For each source it writes a GeoParquet
under ``{SCRUTECH_DATA}/region=aura/<name>/<name>.parquet`` (default data root:
``scrutech/data/``), clipped to the region, and **skips** anything already downloaded.

Resilient by design: every source runs independently in its own try/except, so a moving
endpoint only skips that layer — the rest still download — and the run ends with a
per-source OK/FAILED summary.

⚠️ Endpoints are best-known (2026) but were **not web-verified**. Expect some to need a
fix on first run — the URL of each source is a single constant in ``SOURCES`` below.

Run:  python scrutech/storage/download_aura.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

# Make ``core`` importable when run straight from the repo (no install needed).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core" / "src"))
from core.aoi import fetch_communes  # noqa: E402
from core.io import write_geoparquet  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("scrutech.download")

WGS84 = "EPSG:4326"
GEOAPI = "https://geo.api.gouv.fr"
OVERPASS = "https://overpass-api.de/api/interpreter"

# The 12 départements of Auvergne-Rhône-Alpes.
AURA_DEPTS = ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"]


def data_root() -> Path:
    """Local layout root (env ``SCRUTECH_DATA`` overrides; S3 path later)."""
    root = os.environ.get("SCRUTECH_DATA")
    return Path(root) if root else Path(__file__).resolve().parents[1] / "data"


def _out_path(name: str) -> Path:
    return data_root() / "region=aura" / name / f"{name}.parquet"


# --------------------------------------------------------------------------- #
# Region boundary (geo.api.gouv.fr — verified)                                 #
# --------------------------------------------------------------------------- #
def region_boundary() -> gpd.GeoDataFrame:
    """Union every commune of the 12 AURA départements into one WGS84 polygon (cached).

    Uses the commune FeatureCollection endpoint (the one that actually returns geometry —
    ``/departements/{code}`` does not serve its contour).
    """
    cache = _out_path("boundary")
    if cache.exists():
        return gpd.read_parquet(cache)
    parts = []
    for dept in AURA_DEPTS:
        communes = fetch_communes(dept)
        parts.append(communes)
        logger.info("boundary: dept %s -> %d communes", dept, len(communes))
    allc = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=WGS84)
    region = gpd.GeoDataFrame({"region": ["aura"]}, geometry=[allc.union_all()], crs=WGS84)
    write_geoparquet(region, cache)
    return region


# --------------------------------------------------------------------------- #
# Generic fetchers (mechanisms are correct; only the SOURCES URLs need checking)#
# --------------------------------------------------------------------------- #
def _get_json(url: str, params: dict | None = None, timeout: int = 180) -> dict:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_geojson_url(url: str, **_: object) -> gpd.GeoDataFrame:
    """A GeoJSON (or OGC API Features) endpoint returning a FeatureCollection."""
    gj = _get_json(url)
    return gpd.GeoDataFrame.from_features(gj["features"], crs=WGS84)


def fetch_opendatasoft(base: str, dataset: str, **_: object) -> gpd.GeoDataFrame:
    """Opendatasoft v2.1 export as GeoJSON (Enedis, and most French open-data portals)."""
    url = f"{base}/api/explore/v2.1/catalog/datasets/{dataset}/exports/geojson"
    gj = _get_json(url, {"limit": -1})
    return gpd.GeoDataFrame.from_features(gj.get("features", []), crs=WGS84)


def fetch_overpass(osm_filter: str, region: gpd.GeoDataFrame, **_: object) -> gpd.GeoDataFrame:
    """OSM features via Overpass within the region bbox (then clipped)."""
    minx, miny, maxx, maxy = (round(float(v), 5) for v in region.total_bounds)
    query = f"[out:json][timeout:600];({osm_filter}({miny},{minx},{maxy},{maxx}););out geom;"
    resp = requests.post(OVERPASS, data={"data": query}, timeout=600)
    resp.raise_for_status()
    rows = []
    for el in resp.json().get("elements", []):
        coords = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        if len(coords) >= 2:
            from shapely.geometry import LineString

            rows.append({"osm_id": el.get("id"), "geometry": LineString(coords)})
    return gpd.GeoDataFrame(rows, crs=WGS84)


_FETCHERS = {
    "geojson": fetch_geojson_url,
    "opendatasoft": fetch_opendatasoft,
    "overpass": fetch_overpass,
}


# --------------------------------------------------------------------------- #
# Source registry — fix a URL here if it moved (see the ⚠️ note above)          #
# --------------------------------------------------------------------------- #
SOURCES: list[dict] = [
    {
        "name": "natura2000",
        "kind": "geojson",
        # INPN / data.gouv national SIC+ZPS — VERIFY the exact resource URL.
        "url": "https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
        "&TYPENAMES=PROTECTEDAREAS.SIC:sic&OUTPUTFORMAT=application/json&COUNT=100000",
    },
    {
        "name": "enedis_postes_sources",
        "kind": "opendatasoft",
        "base": "https://opendata.enedis.fr",
        "dataset": "postes-sources",  # VERIFY slug
    },
    {
        "name": "enedis_capacite_accueil",
        "kind": "opendatasoft",
        "base": "https://opendata.enedis.fr",
        "dataset": "capacites-d-accueil-hta-fixees-par-le-s3renr",  # VERIFY slug
    },
    {
        "name": "voirie_osm",
        "kind": "overpass",
        "osm_filter": 'way["highway"~"motorway|trunk|primary|secondary|tertiary"]',
    },
    {
        "name": "fibre_arcep",
        "kind": "geojson",
        # ARCEP déploiement FTTH on data.gouv — VERIFY (may be CSV per dept, not GeoJSON).
        "url": "https://www.data.gouv.fr/api/1/datasets/marche-du-haut-et-tres-haut-debit-"
        "fixe-deploiements/",
    },
    {
        "name": "effis_burnt_areas",
        "kind": "geojson",
        # EFFIS burnt areas (Copernicus/JRC) — VERIFY the download/OGC endpoint.
        "url": "https://maps.effis.emergency.copernicus.eu/effis?service=WFS&version=2.0.0"
        "&request=GetFeature&typeNames=ms:modis.ba.poly&outputFormat=application/json",
    },
    # BDIFF: CSV export by commune (no geometry) — download + join to communes is a
    # separate step (attribute table). Left out of the geo-download for now.
]


def run_source(src: dict, region: gpd.GeoDataFrame) -> tuple[str, str]:
    """Fetch → clip → write one source. Returns (name, status)."""
    name = src["name"]
    out = _out_path(name)
    if out.exists():
        return name, "cached"
    fetcher = _FETCHERS[src["kind"]]
    kwargs = {k: v for k, v in src.items() if k not in ("name", "kind")}
    gdf = fetcher(region=region, **kwargs)
    if gdf.empty:
        return name, "empty"
    clipped = gpd.clip(gdf.to_crs(WGS84), region)
    write_geoparquet(clipped, out)
    return name, f"OK ({len(clipped)} features)"


def main() -> int:
    logger.info("AURA region cache -> %s", data_root() / "region=aura")
    region = region_boundary()
    results = []
    for src in SOURCES:
        try:
            results.append(run_source(src, region))
        except Exception as exc:  # noqa: BLE001 — one bad endpoint must not stop the rest
            results.append((src["name"], f"FAILED — {type(exc).__name__}: {exc} (verify URL)"))
    print("\n=== AURA download summary ===")
    for name, status in results:
        print(f"  {name:<26} {status}")
    print(json.dumps({"root": str(data_root()), "region": "aura"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
