"""The central ScruTech store: one DuckDB file, one schema, idempotent writes.

DuckDB before PostGIS: a single file, no server, spatial + Parquet built in. The DB
holds stats, the AOI registry and the run registry; the map layers themselves stay in
GeoParquet/COG under the same layout (see :mod:`core.storage`).

Every product table carries ``aoi_id``. Writing goes through :func:`replace_partition`,
which deletes the AOI's rows before inserting — so re-running a pillar on an AOI is
idempotent and never leaves orphaned rows.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

# DuckDB est une base de données "embarquée" : pas de serveur à lancer, tout vit dans un
# seul fichier (comme SQLite), mais optimisée pour l'analytique (agrégations, gros volumes)
# et avec une extension "spatial" qui comprend les géométries. On l'utilise ici en Python
# comme une bibliothèque : `duckdb.connect(...)` ouvre le fichier, `.execute(sql)` lance
# des requêtes SQL dessus.
import duckdb

from core.storage import db_path

logger = logging.getLogger("scrutech")

# parents[3] remonte 3 dossiers au-dessus de ce fichier (core/src/core/db.py ->
# core/src/core -> core/src -> core -> scrutech), puis va chercher storage/schema.sql :
# le fichier SQL qui définit toutes les tables de la base centrale.
SCHEMA_SQL = Path(__file__).resolve().parents[3] / "storage" / "schema.sql"


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the central store: spatial loaded, schema applied (both idempotent).

    ``read_only`` skips the schema step (front-ends only read).
    """
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)  # crée le dossier parent s'il n'existe pas
    con = duckdb.connect(str(target), read_only=read_only)
    _load_spatial(con)
    if not read_only:
        # Les front-ends (plugin QGIS, dashboard) ouvrent la base en lecture seule : ils
        # n'ont pas besoin (et n'ont pas le droit) de créer/modifier les tables.
        apply_schema(con)
    return con


def _load_spatial(con: duckdb.DuckDBPyConnection) -> None:
    """Load the spatial extension (installing it once if needed)."""
    try:
        # Si l'extension est déjà installée (téléchargée) sur cette machine, LOAD suffit.
        con.execute("LOAD spatial")
    except duckdb.Error:
        # Sinon on l'installe une bonne fois (comme `pip install`, mais pour une extension
        # DuckDB), puis on la charge. Les appels suivants passeront directement par le `try`.
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")


def apply_schema(con: duckdb.DuckDBPyConnection, schema: Path | None = None) -> None:
    """Apply ``storage/schema.sql`` — every statement is CREATE ... IF NOT EXISTS."""
    # "IF NOT EXISTS" dans le SQL rend cette opération "idempotente" : l'exécuter
    # plusieurs fois de suite ne provoque pas d'erreur ni de duplication, une table déjà
    # présente est simplement laissée telle quelle.
    sql = (schema or SCHEMA_SQL).read_text(encoding="utf-8")
    con.execute(sql)


def replace_partition(
    con: duckdb.DuckDBPyConnection,
    table: str,
    aoi_id: str,
    df: Any,
    extra_keys: dict[str, Any] | None = None,
) -> int:
    """Idempotently write one AOI's partition: DELETE its rows, then INSERT ``df``.

    ``extra_keys`` narrows the partition further (e.g. ``{"y0": 2018, "y1": 2025}``).
    A GeoDataFrame's geometry is stored as DuckDB GEOMETRY (via WKB). Returns the
    number of rows inserted.
    """
    # On construit la clause WHERE dynamiquement : toujours "aoi_id = ?", plus une
    # condition par clé supplémentaire dans extra_keys (ex: année, fenêtre temporelle).
    # Les "?" sont des PLACEHOLDERS : DuckDB insère lui-même les valeurs de `params` à
    # leur place de façon sûre (requête préparée). C'est la protection standard contre
    # l'injection SQL — on n'insère JAMAIS une valeur utilisateur directement dans le
    # texte de la requête, seulement les noms de colonnes/table (qui viennent du code,
    # pas d'une entrée utilisateur).
    conditions = ['"aoi_id" = ?']
    params: list[Any] = [aoi_id]
    for key, value in (extra_keys or {}).items():
        conditions.append(f'"{key}" = ?')
        params.append(value)
    con.execute(f'DELETE FROM "{table}" WHERE ' + " AND ".join(conditions), params)

    frame = _with_wkb(df)
    if len(frame) == 0:
        # Rien à insérer : on s'arrête après le DELETE. Le partition (aoi, extra_keys)
        # existe désormais mais est vide — c'est voulu (ex: un pilier qui ne trouve rien
        # sur cette AOI doit "vider" son ancien résultat, pas le laisser périmé).
        logger.info("replace_partition: %s aoi=%s -> 0 row (partition cleared)", table, aoi_id)
        return 0

    cols = ", ".join(f'"{c}"' for c in frame.columns)
    # ST_GeomFromWKB reconstruit une géométrie DuckDB à partir des octets WKB (voir
    # _with_wkb ci-dessous) ; les autres colonnes sont insérées telles quelles.
    select = ", ".join("ST_GeomFromWKB(geom)" if c == "geom" else f'"{c}"' for c in frame.columns)
    # register() rend un DataFrame pandas/geopandas visible depuis le SQL DuckDB, sous un
    # nom temporaire ("_incoming") — comme si c'était une table. On peut alors faire un
    # INSERT ... SELECT depuis ce "faux tableau" directement en SQL, sans boucle Python
    # ligne par ligne (bien plus rapide).
    con.register("_incoming", frame)
    try:
        con.execute(f'INSERT INTO "{table}" ({cols}) SELECT {select} FROM _incoming')
    finally:
        # Le "finally" garantit le nettoyage même si l'INSERT échoue en cours de route.
        con.unregister("_incoming")
    logger.info("replace_partition: %s aoi=%s -> %d rows", table, aoi_id, len(frame))
    return len(frame)


def _with_wkb(df: Any) -> Any:
    """GeoDataFrame -> plain DataFrame whose geometry became a WKB ``geom`` column."""
    # DuckDB ne sait pas lire nativement un objet géométrique shapely en mémoire : on le
    # convertit d'abord en WKB (Well-Known Binary — une suite d'octets qui encode
    # n'importe quelle géométrie), que DuckDB pourra reconvertir avec ST_GeomFromWKB.
    geom_col = getattr(df, "_geometry_column_name", None)
    if geom_col is None or geom_col not in getattr(df, "columns", []):
        # Pas un GeoDataFrame (ou pas de colonne géométrie) : rien à convertir, on renvoie tel quel.
        return df
    out = df.drop(columns=[geom_col])
    out["geom"] = df[geom_col].to_wkb()
    return out
