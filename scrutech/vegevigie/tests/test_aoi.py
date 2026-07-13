"""AOI geometry tests — pure functions on synthetic communes, no network."""

import geopandas as gpd
from shapely.geometry import Polygon

from vegevigie.aoi import WGS84, build_aoi, clip_to_bbox, dissolve_boundary


def _synthetic_communes() -> gpd.GeoDataFrame:
    # Three unit squares in a row along longitude at lat 44-45.
    polys = [
        Polygon([(4.0, 44.0), (5.0, 44.0), (5.0, 45.0), (4.0, 45.0)]),
        Polygon([(5.0, 44.0), (6.0, 44.0), (6.0, 45.0), (5.0, 45.0)]),
        Polygon([(6.0, 44.0), (7.0, 44.0), (7.0, 45.0), (6.0, 45.0)]),
    ]
    return gpd.GeoDataFrame(
        {"code": ["07001", "07002", "07003"], "nom": ["A", "B", "C"]},
        geometry=polys,
        crs=WGS84,
    )


def test_clip_to_bbox_selects_overlapping_communes() -> None:
    communes = _synthetic_communes()
    # bbox overlaps only the first two squares.
    selected = clip_to_bbox(communes, (4.2, 44.2, 5.5, 44.8))
    assert set(selected["code"]) == {"07001", "07002"}


def test_clip_keeps_whole_commune_geometry() -> None:
    communes = _synthetic_communes()
    selected = clip_to_bbox(communes, (4.9, 44.4, 5.1, 44.6))  # tiny bbox straddling A/B edge
    # Communes A and B are included whole (bounds unchanged), not cut to the bbox.
    assert set(selected["code"]) == {"07001", "07002"}
    assert tuple(selected.total_bounds) == (4.0, 44.0, 6.0, 45.0)


def test_dissolve_boundary_merges_to_single_polygon() -> None:
    merged = dissolve_boundary(_synthetic_communes(), "ardeche")
    assert len(merged) == 1
    assert merged.iloc[0]["name"] == "ardeche"
    # Three unit squares fused into one polygon spanning the full extent.
    assert tuple(merged.total_bounds) == (4.0, 44.0, 7.0, 45.0)
    assert merged.geometry.iloc[0].geom_type == "Polygon"


def test_build_aoi_skips_when_cached(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    def fake_fetch(dept: str, timeout: int = 60) -> gpd.GeoDataFrame:
        calls["n"] += 1
        return _synthetic_communes()

    monkeypatch.setattr("vegevigie.aoi.fetch_communes", fake_fetch)

    c1, a1 = build_aoi("07", "ardeche", tmp_path, small_bbox=(4.2, 44.2, 5.5, 44.8))
    assert c1.exists() and a1.exists()
    assert calls["n"] == 1

    # Second call with outputs present must not re-fetch.
    build_aoi("07", "ardeche", tmp_path, small_bbox=(4.2, 44.2, 5.5, 44.8))
    assert calls["n"] == 1

    # --force re-fetches.
    build_aoi("07", "ardeche", tmp_path, small_bbox=(4.2, 44.2, 5.5, 44.8), force=True)
    assert calls["n"] == 2


def test_build_aoi_full_writes_dissolved_outline(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "vegevigie.aoi.fetch_communes", lambda dept, timeout=60: _synthetic_communes()
    )
    _, aoi_path = build_aoi("07", "ardeche", tmp_path, small_bbox=None)
    aoi = gpd.read_parquet(aoi_path)
    assert len(aoi) == 1  # dissolved to a single outline
