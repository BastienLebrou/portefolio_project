"""Persistence helpers: GeoParquet for geometry, DuckDB for querying/ranking.

The commune-level results live in two complementary stores (CLAUDE.md §1.7):

- **GeoParquet** — the full layer *with geometry*, ready to open in QGIS or reload
  with GeoPandas.
- **DuckDB** — the same attributes as a SQL table (geometry dropped) so commune
  rankings are a plain ``SELECT ... ORDER BY``. DuckDB is embedded (no server) and
  reads/writes a single file.

I/O only — no analysis here (that's :mod:`vegevigie.zonal`).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd


def write_geoparquet(gdf: gpd.GeoDataFrame, path: Path) -> Path:
    """Write a GeoDataFrame to GeoParquet (creating parent dirs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path)
    return path


def write_gpkg(gdf: gpd.GeoDataFrame, path: Path, layer: str = "stats") -> Path:
    """Write a GeoDataFrame to a GeoPackage — the QGIS-facing twin of the
    GeoParquet output (every QGIS build reads GPKG; Parquet needs a GDAL driver
    that not all builds ship)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path, driver="GPKG", layer=layer)
    return path


def write_duckdb(df: pd.DataFrame, db_path: Path, table: str) -> Path:
    """Write a (geometry-free) DataFrame to a DuckDB table, replacing it if present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tabular = df.drop(columns="geometry", errors="ignore")
    con = duckdb.connect(str(db_path))
    try:
        con.register("_incoming", tabular)
        con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _incoming')
        con.unregister("_incoming")
    finally:
        con.close()
    return db_path


def rank_communes(
    db_path: Path,
    metric: str,
    table: str = "commune_stats",
    ascending: bool = False,
    limit: int = 10,
) -> pd.DataFrame:
    """Return the top ``limit`` communes ordered by ``metric`` (desc by default).

    ``ascending=True`` surfaces the most browning / most drought-stressed communes.
    """
    order = "ASC" if ascending else "DESC"
    con = duckdb.connect(str(db_path))
    try:
        return con.execute(
            f'SELECT * FROM "{table}" '
            f'WHERE "{metric}" IS NOT NULL '
            f'ORDER BY "{metric}" {order} '
            f"LIMIT {int(limit)}"
        ).df()
    finally:
        con.close()
