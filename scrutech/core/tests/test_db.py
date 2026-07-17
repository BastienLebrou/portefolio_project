"""core.db offline tests — schema is idempotent, writes are partition-replacing."""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from core.db import apply_schema, connect, replace_partition


def _stats(aoi_id: str, n: int) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "aoi_id": [aoi_id] * n,
            "insee": [f"0700{i}" for i in range(n)],
            "nom": [f"C{i}" for i in range(n)],
            "y0": [2018] * n,
            "y1": [2025] * n,
            "mean_sen_slope": [0.01 * i for i in range(n)],
        },
        geometry=[box(i, i, i + 1, i + 1) for i in range(n)],
        crs="EPSG:4326",
    )


def test_connect_creates_store_with_tables(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    names = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert {"aoi", "product_runs", "vege_commune_stats", "sdbpi_batiments"} <= names
    con.close()


def test_apply_schema_is_idempotent(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    apply_schema(con)  # second application must not raise
    apply_schema(con)
    con.close()


def test_replace_partition_inserts_then_replaces(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    assert (
        replace_partition(con, "vege_commune_stats", "insee-07005", _stats("insee-07005", 3)) == 3
    )
    # Re-running the same AOI replaces its rows instead of duplicating them.
    replace_partition(con, "vege_commune_stats", "insee-07005", _stats("insee-07005", 2))
    n = con.execute(
        "SELECT count(*) FROM vege_commune_stats WHERE aoi_id = 'insee-07005'"
    ).fetchone()[0]
    assert n == 2
    con.close()


def test_replace_partition_isolates_other_aois(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    replace_partition(con, "vege_commune_stats", "insee-07005", _stats("insee-07005", 2))
    replace_partition(con, "vege_commune_stats", "insee-26001", _stats("insee-26001", 3))
    replace_partition(con, "vege_commune_stats", "insee-07005", _stats("insee-07005", 1))
    counts = dict(
        con.execute("SELECT aoi_id, count(*) FROM vege_commune_stats GROUP BY aoi_id").fetchall()
    )
    assert counts == {"insee-07005": 1, "insee-26001": 3}
    con.close()


def test_geometry_roundtrips_as_duckdb_geometry(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    replace_partition(con, "vege_commune_stats", "insee-07005", _stats("insee-07005", 1))
    wkt = con.execute("SELECT ST_AsText(geom) FROM vege_commune_stats").fetchone()[0]
    assert wkt.startswith("POLYGON")
    con.close()


def test_replace_partition_with_extra_keys(tmp_path: Path) -> None:
    con = connect(tmp_path / "s.duckdb")
    rows = pd.DataFrame(
        {"aoi_id": ["a"], "y0": [2018], "y1": [2025], "month": [None], "anomaly_mean": [0.5]}
    )
    replace_partition(con, "vege_timeline", "a", rows, extra_keys={"y0": 2018, "y1": 2025})
    replace_partition(con, "vege_timeline", "a", rows, extra_keys={"y0": 2018, "y1": 2025})
    assert con.execute("SELECT count(*) FROM vege_timeline").fetchone()[0] == 1
    con.close()
