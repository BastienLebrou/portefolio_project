"""Local GeoParquet cache of AlphaEarth embeddings, per AOI + year — idempotent.

CE QUE ÇA FAIT : met en cache les embeddings téléchargés depuis GEE pour ne pas
re-requêter (ni re-payer le quota) à chaque session.

POURQUOI GeoParquet et non GeoTIFF : chaque « pixel » est un point avec 64 attributs
numériques. Parquet est colonnaire → lire les bandes 0-10 pour un KNN rapide lit 10/64
colonnes, pas le raster entier.

Le chemin suit le layout ScruTech (``core.storage``) : ``alphaearth/aoi=<id>/embeddings/
<year>/embeddings.parquet``, avec une provenance en side-car JSON.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import geopandas as gpd
from core.storage import product_path

DATASET_VERSION = "GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL"


def cache_path(aoi_id: str, year: int) -> Path:
    """Where the embeddings of one (AOI, year) live."""
    return product_path("alphaearth", aoi_id, "embeddings", str(year), "embeddings.parquet")


def has(aoi_id: str, year: int) -> bool:
    """True if this (AOI, year) is already cached (skip the GEE request)."""
    return cache_path(aoi_id, year).exists()


def write(
    gdf: gpd.GeoDataFrame,
    aoi_id: str,
    year: int,
    quota_pixels: int | None = None,
    dataset_version: str = DATASET_VERSION,
) -> Path:
    """Write embeddings + a provenance side-car; returns the parquet path (idempotent write)."""
    path = cache_path(aoi_id, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    # compression="zstd" : un algorithme de compression rapide et efficace (meilleur
    # compromis vitesse/taille que le gzip classique), standard pour Parquet aujourd'hui.
    gdf.to_parquet(path, compression="zstd", index=False)
    # Un fichier "side-car" (à côté) .json documente D'OÙ vient ce cache : utile plus
    # tard pour savoir si le résultat est encore à jour, ou pour du débogage.
    provenance = {
        "aoi_id": aoi_id,
        "year": year,
        "dataset_version": dataset_version,
        "downloaded_at": dt.datetime.now(dt.UTC).isoformat(),
        "n_pixels": int(len(gdf)),
        "quota_pixels": quota_pixels,
        "bbox_wgs84": [float(v) for v in gdf.to_crs("EPSG:4326").total_bounds],
    }
    path.with_suffix(".json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return path


def read(aoi_id: str, year: int) -> gpd.GeoDataFrame:
    """Read the cached embeddings of one (AOI, year)."""
    return gpd.read_parquet(cache_path(aoi_id, year))
