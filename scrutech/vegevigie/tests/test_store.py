"""Store tests — DuckDB write + ranking query round-trip, no network (§8)."""

import geopandas as gpd
from shapely.geometry import Point

from vegevigie.store import rank_communes, write_duckdb, write_geoparquet


def _stats_gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "code": ["A", "B", "C"],
            "nom": ["Alpha", "Beta", "Gamma"],
            "mean_sen_slope": [0.03, -0.01, 0.005],
            "mean_anomaly": [-0.2, -1.5, 0.4],
        },
        geometry=[Point(0, 0), Point(1, 1), Point(2, 2)],
        crs="EPSG:4326",
    )


def test_write_geoparquet_roundtrip(tmp_path) -> None:
    path = write_geoparquet(_stats_gdf(), tmp_path / "communes.parquet")
    assert path.exists()
    back = gpd.read_parquet(path)
    assert len(back) == 3
    assert "geometry" in back


def test_duckdb_write_drops_geometry(tmp_path) -> None:
    db = write_duckdb(_stats_gdf(), tmp_path / "v.duckdb", table="commune_stats")
    assert db.exists()
    top = rank_communes(db, metric="mean_sen_slope", limit=10)
    assert "geometry" not in top.columns


def test_rank_top_greening(tmp_path) -> None:
    db = write_duckdb(_stats_gdf(), tmp_path / "v.duckdb", table="commune_stats")
    top = rank_communes(db, metric="mean_sen_slope", ascending=False, limit=1)
    assert top.iloc[0]["code"] == "A"  # highest slope


def test_rank_most_drought(tmp_path) -> None:
    db = write_duckdb(_stats_gdf(), tmp_path / "v.duckdb", table="commune_stats")
    driest = rank_communes(db, metric="mean_anomaly", ascending=True, limit=1)
    assert driest.iloc[0]["code"] == "B"  # most negative anomaly
