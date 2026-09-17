"""Vector IO shared across pillars — the single reader/writer.

``read_vector`` replaces the three near-identical loaders that lived in
``vegevigie.interface``, ``sdbpi`` and ``mini_dc``.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd


def read_vector(path: str | Path) -> gpd.GeoDataFrame:
    """Read any vector layer: GeoParquet by ``.parquet`` suffix, else GDAL (gpkg/shp/geojson)."""
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        return gpd.read_parquet(p)
    return gpd.read_file(p)


def write_geoparquet(gdf: gpd.GeoDataFrame, path: str | Path) -> Path:
    """Write a GeoDataFrame to GeoParquet (creating parent dirs); return the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(p)
    return p
