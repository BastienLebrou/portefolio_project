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


def authenticate_gee(auth_id: str = "gee_service") -> None:
    """Initialize GEE from a service-account JSON stored in QgsAuthManager (never on disk).

    Store the JSON under the config key ``json_credentials`` of the auth entry ``auth_id``.
    """
    import json

    import ee
    from qgis.core import QgsApplication

    config = QgsApplication.authManager().authMethodConfig(auth_id)
    creds = json.loads(config.configMap()["json_credentials"])
    ee.Initialize(
        credentials=ee.ServiceAccountCredentials(creds["client_email"], key_data=json.dumps(creds))
    )


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
