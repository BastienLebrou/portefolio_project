"""Interface (WUI) tests — pure geometry on synthetic layers, no network (§8)."""

import geopandas as gpd
from shapely.geometry import box

from vegevigie.interface import build_interface, forest_bati_interface

L93 = "EPSG:2154"


def _forest() -> gpd.GeoDataFrame:
    # 100 m x 100 m forest block at the origin (Lambert-93 metres).
    return gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 100, 100)], crs=L93)


def _bati(minx: float) -> gpd.GeoDataFrame:
    # 20 m x 20 m building pad starting at x=minx, centred on the forest's mid-height.
    return gpd.GeoDataFrame({"id": [1]}, geometry=[box(minx, 40, minx + 20, 60)], crs=L93)


def test_contact_produces_line_zone_and_metrics() -> None:
    # Building 20 m from the forest edge, contact_m=50 -> a real frontier + band.
    res = forest_bati_interface(_forest(), _bati(120), metric_crs=L93, contact_m=50)
    assert res.metrics["interface_length_m"] > 0
    assert 0 < res.metrics["interface_zone_ha"] < 1.0  # a strip, not the whole block
    assert res.metrics["bati_area_ha"] > 0


def test_no_contact_returns_zero_metrics_not_crash() -> None:
    # Building 100 m away, beyond contact_m=50 -> empty geometries, zero metrics.
    res = forest_bati_interface(_forest(), _bati(200), metric_crs=L93, contact_m=50)
    assert res.metrics["interface_length_m"] == 0.0
    assert res.metrics["interface_zone_ha"] == 0.0


def test_aoi_clips_the_frontier() -> None:
    full = forest_bati_interface(_forest(), _bati(120), metric_crs=L93, contact_m=50)
    half = forest_bati_interface(
        _forest(),
        _bati(120),
        metric_crs=L93,
        contact_m=50,
        aoi=gpd.GeoDataFrame(geometry=[box(0, 0, 200, 50)], crs=L93),  # lower half only
    )
    assert 0 < half.metrics["interface_length_m"] < full.metrics["interface_length_m"]


def test_reprojects_inputs_to_metric_crs() -> None:
    # Inputs in WGS84 must be brought back to the metric CRS before any maths.
    res = forest_bati_interface(
        _forest().to_crs("EPSG:4326"),
        _bati(120).to_crs("EPSG:4326"),
        metric_crs=L93,
        contact_m=50,
    )
    assert res.line.crs.to_string() == L93
    assert res.metrics["interface_length_m"] > 0


def test_build_interface_writes_parquet_and_geojson(tmp_path) -> None:
    forest_path = tmp_path / "forest.parquet"
    bati_path = tmp_path / "bati.parquet"
    _forest().to_parquet(forest_path)
    _bati(120).to_parquet(bati_path)

    line_path, zone_path, metrics = build_interface(
        forest_path=forest_path,
        bati_path=bati_path,
        out_dir=tmp_path / "out",
        metric_crs=L93,
        contact_m=50.0,
    )
    assert line_path.exists() and zone_path.exists()
    assert (tmp_path / "out" / "interface_line.geojson").exists()
    assert (tmp_path / "out" / "interface_zone.geojson").exists()
    assert metrics["interface_length_m"] > 0
