"""core.io offline tests — the single vector reader/writer, roundtrips."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from core.io import read_vector, write_geoparquet


def _gdf() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"k": [1]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")


def test_read_vector_parquet(tmp_path: Path) -> None:
    p = write_geoparquet(_gdf(), tmp_path / "x.parquet")
    out = read_vector(p)
    assert len(out) == 1
    assert out.crs.to_epsg() == 4326


def test_read_vector_gpkg(tmp_path: Path) -> None:
    p = tmp_path / "x.gpkg"
    _gdf().to_file(p, driver="GPKG")
    assert len(read_vector(p)) == 1


def test_write_geoparquet_creates_dirs(tmp_path: Path) -> None:
    p = write_geoparquet(_gdf(), tmp_path / "sub" / "x.parquet")
    assert p.exists()
