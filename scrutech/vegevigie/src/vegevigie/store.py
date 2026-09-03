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


def write_duckdb(df: pd.DataFrame, db_path: Path, table: str) -> Path:
    """Write a (geometry-free) DataFrame to a DuckDB table, replacing it if present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # errors="ignore" : ne pas planter si la colonne "geometry" n'existe pas (df était
    # déjà un DataFrame simple, pas un GeoDataFrame) — DuckDB (sans son extension
    # spatial ici) ne saurait pas stocker une géométrie shapely telle quelle.
    tabular = df.drop(columns="geometry", errors="ignore")
    con = duckdb.connect(str(db_path))
    try:
        # Comme dans core.db.replace_partition : register() rend le DataFrame visible
        # depuis le SQL sous un nom temporaire, pour l'insérer via un simple SELECT
        # plutôt que ligne par ligne en Python.
        con.register("_incoming", tabular)
        # `table` vient toujours du code appelant (jamais d'une saisie utilisateur),
        # donc l'interpoler dans le SQL est sûr ici — contrairement à une VALEUR de
        # donnée, un nom de table ne peut pas passer par un paramètre `?` de toute façon.
        con.execute(f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _incoming')
        con.unregister("_incoming")
    finally:
        # Le `finally` garantit la fermeture de la connexion même si l'écriture échoue.
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
        # `table`, `metric` et `order` sont interpolés directement dans le texte SQL
        # (pas de "?") : ce sont des noms de colonne/table et un mot-clé fixe ("ASC"/
        # "DESC"), jamais une VALEUR de donnée — le seul endroit où l'injection SQL est
        # un vrai risque est quand une valeur arbitraire venue de l'utilisateur finit
        # dans le texte de la requête, ce qui n'est pas le cas ici. `int(limit)` force
        # explicitement un entier, ce qui empêche justement ce risque sur ce paramètre.
        return con.execute(
            f'SELECT * FROM "{table}" '
            f'WHERE "{metric}" IS NOT NULL '
            f'ORDER BY "{metric}" {order} '
            f"LIMIT {int(limit)}"
        ).df()  # .df() renvoie directement un DataFrame pandas plutôt qu'un curseur brut
    finally:
        con.close()
