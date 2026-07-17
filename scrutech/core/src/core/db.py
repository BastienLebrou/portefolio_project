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

import duckdb

from core.storage import db_path

logger = logging.getLogger("scrutech")

SCHEMA_SQL = Path(__file__).resolve().parents[3] / "storage" / "schema.sql"


def connect(path: str | Path | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open the central store: spatial loaded, schema applied (both idempotent).

    ``read_only`` skips the schema step (front-ends only read).
    """
    target = Path(path) if path else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(target), read_only=read_only)
    _load_spatial(con)
    if not read_only:
        apply_schema(con)
    return con


def _load_spatial(con: duckdb.DuckDBPyConnection) -> None:
    """Load the spatial extension (installing it once if needed)."""
    try:
        con.execute("LOAD spatial")
    except duckdb.Error:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")


def apply_schema(con: duckdb.DuckDBPyConnection, schema: Path | None = None) -> None:
    """Apply ``storage/schema.sql`` — every statement is CREATE ... IF NOT EXISTS."""
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
    conditions = ['"aoi_id" = ?']
    params: list[Any] = [aoi_id]
    for key, value in (extra_keys or {}).items():
        conditions.append(f'"{key}" = ?')
        params.append(value)
    con.execute(f'DELETE FROM "{table}" WHERE ' + " AND ".join(conditions), params)

    frame = _with_wkb(df)
    if len(frame) == 0:
        logger.info("replace_partition: %s aoi=%s -> 0 row (partition cleared)", table, aoi_id)
        return 0

    cols = ", ".join(f'"{c}"' for c in frame.columns)
    select = ", ".join("ST_GeomFromWKB(geom)" if c == "geom" else f'"{c}"' for c in frame.columns)
    con.register("_incoming", frame)
    try:
        con.execute(f'INSERT INTO "{table}" ({cols}) SELECT {select} FROM _incoming')
    finally:
        con.unregister("_incoming")
    logger.info("replace_partition: %s aoi=%s -> %d rows", table, aoi_id, len(frame))
    return len(frame)


def _with_wkb(df: Any) -> Any:
    """GeoDataFrame -> plain DataFrame whose geometry became a WKB ``geom`` column."""
    geom_col = getattr(df, "_geometry_column_name", None)
    if geom_col is None or geom_col not in getattr(df, "columns", []):
        return df
    out = df.drop(columns=[geom_col])
    out["geom"] = df[geom_col].to_wkb()
    return out
