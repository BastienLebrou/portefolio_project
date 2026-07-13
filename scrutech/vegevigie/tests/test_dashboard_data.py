"""Dashboard helper tests — colour mapping + output discovery, no UI, no network."""

import geopandas as gpd
from shapely.geometry import box

from vegevigie.dashboard.data import NO_DATA_COLOR, find_outputs, slope_color


def test_slope_color_diverges_and_is_valid_hex() -> None:
    greening = slope_color(0.02)
    browning = slope_color(-0.02)
    for color in (greening, browning):
        assert color.startswith("#") and len(color) == 7
    assert greening != browning
    # RdYlGn: greening end is green-dominant, browning end is red-dominant.
    assert _g(greening) > _r(greening)
    assert _r(browning) > _g(browning)


def test_slope_color_none_and_nan_are_neutral() -> None:
    assert slope_color(None) == NO_DATA_COLOR
    assert slope_color(float("nan")) == NO_DATA_COLOR


def test_slope_color_clamps_beyond_limits() -> None:
    assert slope_color(0.02) == slope_color(0.5)  # both clamp to the green extreme
    assert slope_color(-0.02) == slope_color(-0.5)


def test_find_outputs_empty_dir_not_ready(tmp_path) -> None:
    out = find_outputs(tmp_path)
    assert not out.ready()
    assert out.zonal is None and out.duckdb is None and out.timeline is None


def test_find_outputs_discovers_and_picks_latest(tmp_path) -> None:
    gdf = gpd.GeoDataFrame({"nom": ["A"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326")
    (tmp_path / "zonal_stats_2018_2020.parquet").write_bytes(b"")  # placeholder
    gdf.to_parquet(tmp_path / "zonal_stats_2018_2025.parquet")
    (tmp_path / "vegevigie.duckdb").write_bytes(b"")
    (tmp_path / "drought_timeline_2018_2025.parquet").write_bytes(b"")

    out = find_outputs(tmp_path)
    assert out.ready()
    assert out.zonal.name == "zonal_stats_2018_2025.parquet"  # lexically last window
    assert out.duckdb is not None and out.timeline is not None


def _r(hex_color: str) -> int:
    return int(hex_color[1:3], 16)


def _g(hex_color: str) -> int:
    return int(hex_color[3:5], 16)
