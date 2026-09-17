"""Vector IO shared across pillars — the single reader/writer.

``read_vector`` replaces the three near-identical loaders that lived in
``vegevigie.interface``, ``sdbpi`` and ``mini_dc``.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd


def read_vector(path: str | Path) -> gpd.GeoDataFrame:
    """Read any vector layer: GeoParquet by ``.parquet`` suffix, else GDAL (gpkg/shp/geojson)."""
    # "Vecteur" en SIG = des données géométriques (points/lignes/polygones), par
    # opposition au "raster" (une grille de pixels, comme une image satellite).
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        # GeoParquet : un format de fichier colonne (le format "Parquet" du monde
        # data/big data) étendu pour stocker une colonne géométrie. Très compact et
        # rapide à lire, c'est le format que ScruTech utilise pour stocker ses résultats.
        return gpd.read_parquet(p)
    # Pour tous les autres formats (.gpkg GeoPackage, .shp Shapefile, .geojson...),
    # geopandas délègue à GDAL/Fiona qui sait les reconnaître à partir de l'extension.
    return gpd.read_file(p)


def write_geoparquet(gdf: gpd.GeoDataFrame, path: str | Path) -> Path:
    """Write a GeoDataFrame to GeoParquet (creating parent dirs); return the path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)  # crée les dossiers manquants du chemin
    gdf.to_parquet(p)
    return p
