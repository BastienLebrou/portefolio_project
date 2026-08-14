"""Google Earth Engine client for AlphaEarth embeddings — auth via QgsAuthManager.

CE QUE ÇA FAIT : se connecte à GEE, requête le dataset annuel AlphaEarth pour une AOI
et une année, renvoie un GeoDataFrame de pixels (un point × 64 colonnes A00…A63).

POURQUOI GEE et non STAC/COG : AlphaEarth (``GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL``)
n'est servi **que** sur Earth Engine (ni CDSE ni Planetary Computer). L'auth est un
service-account JSON (vs le token Bearer de STAC) — deux patterns différents.

COÛT (question geo-data engineer) : chaque requête consomme le quota GEE. On estime
avant (``estimate_gee_cost``) et on met en cache (``alphaearth.store``) pour ne jamais
re-télécharger. Clé jamais en dur : elle vient de QgsAuthManager.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape

from alphaearth._columns import EMB_COLS

DATASET = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


@dataclass
class AlphaEarthQuery:
    """One embeddings request: an AOI geometry, a year, and cost guard-rails."""

    aoi_geojson: dict
    year: int
    band_indices: list[int] | None = None  # subset of the 64 bands (None = all)
    max_pixels: int = 500_000  # GEE cost guard-rail


def estimate_gee_cost(aoi_km2: float) -> dict:
    """Estimate the GEE pixels to download — check the bill before ordering.

    The free GEE quota is limited; a 100 km² AOI at 10 m = 1e6 pixels × 64 bands is heavy.
    """
    pixels = int(aoi_km2 * 1e6 / 100)  # 10 m² per pixel
    return {
        "pixel_count": pixels,
        "estimated_size_mb": round(pixels * 64 * 4 / 1e6, 1),  # float32
        "quota_impact": "faible" if pixels < 500_000 else "élevé",
        "recommendation": "local RF" if pixels < 1_000_000 else "exporter par tuiles",
    }


def authenticate_gee(auth_id: str = "gee_service", credentials_json: str | None = None) -> None:
    """Initialize GEE from a service-account JSON (never on disk).

    Credential source, in order: the ``credentials_json`` argument → the
    ``SCRUTECH_GEE_CREDENTIALS`` environment variable (how the QGIS plugin passes it to
    the external interpreter, which has no QgsAuthManager) → QgsAuthManager entry
    ``auth_id`` (config key ``json_credentials``, for in-QGIS use).
    """
    import json
    import os

    import ee

    raw = credentials_json or os.environ.get("SCRUTECH_GEE_CREDENTIALS")
    if raw is None:
        from qgis.core import QgsApplication

        config = QgsApplication.authManager().authMethodConfig(auth_id)
        raw = config.configMap()["json_credentials"]
    creds = json.loads(raw)
    ee.Initialize(
        credentials=ee.ServiceAccountCredentials(creds["client_email"], key_data=json.dumps(creds)),
        project=creds.get("project_id"),
    )


def _annual_image(geom, year: int):
    """The single AlphaEarth annual embedding image (64 bands) over ``geom`` for ``year``."""
    import ee

    return (
        ee.ImageCollection(DATASET)
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .filterBounds(geom)
        .first()
    )


def _cosine_distance_image(img1, img2):
    """Server-side per-pixel cosine distance (1 − cosine) between two 64-band images.

    Doing this on GEE avoids the pixel-alignment problem: two independent ``sample`` calls
    would return different point sets across years, so a client-side row merge would be
    meaningless. One image, one sample, one aligned ``change_distance`` per pixel.
    """
    import ee

    dot = img1.multiply(img2).reduce(ee.Reducer.sum())
    n1 = img1.multiply(img1).reduce(ee.Reducer.sum()).sqrt()
    n2 = img2.multiply(img2).reduce(ee.Reducer.sum()).sqrt()
    cosine = dot.divide(n1.multiply(n2))
    return ee.Image(1).subtract(cosine).rename("change_distance")


def fetch_change_samples(
    aoi_geojson: dict, year1: int, year2: int, max_pixels: int = 500_000
) -> gpd.GeoDataFrame:
    """Sample the year1→year2 cosine-change surface over the AOI (WGS84 points).

    Returns a GeoDataFrame with a single ``change_distance`` column (+ geometry). Requires
    :func:`authenticate_gee` first.
    """
    import ee

    geom = ee.Geometry(aoi_geojson)
    dist = _cosine_distance_image(_annual_image(geom, year1), _annual_image(geom, year2))
    sample = dist.sample(region=geom, scale=10, numPixels=max_pixels, geometries=True)
    return _dist_features_to_gdf(sample.getInfo()["features"])


def _dist_features_to_gdf(features: list[dict]) -> gpd.GeoDataFrame:
    """Parse a sampled ``change_distance`` FeatureCollection to a GDF (pure, testable)."""
    rows = [
        {"pixel_id": i, "change_distance": f.get("properties", {}).get("change_distance")}
        for i, f in enumerate(features)
    ]
    geoms = [shape(f["geometry"]) for f in features]
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs="EPSG:4326")


def _features_to_gdf(features: list[dict]) -> gpd.GeoDataFrame:
    """Convert a GEE ``FeatureCollection.getInfo()['features']`` list to a GDF (pure, testable)."""
    rows = []
    geoms = []
    for i, feat in enumerate(features):
        props = feat.get("properties", {})
        row: dict = {"pixel_id": i}
        for col in EMB_COLS:
            row[col] = props.get(col)
        rows.append(row)
        geoms.append(shape(feat["geometry"]))
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=geoms, crs="EPSG:4326")


def fetch_embeddings(query: AlphaEarthQuery) -> gpd.GeoDataFrame:
    """Query GEE for the AOI/year and return a GDF of pixels with the 64 embedding columns.

    Requires :func:`authenticate_gee` first. Samples at 10 m up to ``max_pixels`` points.
    """
    import ee

    geom = ee.Geometry(query.aoi_geojson)
    image = (
        ee.ImageCollection(DATASET)
        .filterDate(f"{query.year}-01-01", f"{query.year}-12-31")
        .filterBounds(geom)
        .first()
    )
    if query.band_indices is not None:
        image = image.select([EMB_COLS[i] for i in query.band_indices])
    sample = image.sample(region=geom, scale=10, numPixels=query.max_pixels, geometries=True)
    return _features_to_gdf(sample.getInfo()["features"])
