"""SDBPi pure-function tests — filter / spatial join / status, synthetic data, no network."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Point, box

import processing

L93 = "EPSG:2154"
USAGES = frozenset({"Commercial et services", "Industriel"})


def _bati(usage: str, minx: float) -> dict:
    return {"cleabs": f"b-{minx:.0f}", "usage_1": usage, "usage_2": None,
            "geometry": box(minx, 6_400_000, minx + 20, 6_400_020)}


def test_filter_professional_keeps_target_usages() -> None:
    bati = gpd.GeoDataFrame(
        [_bati("Commercial et services", 900_000), _bati("Résidentiel", 900_100)], crs=L93
    )
    kept = processing.filter_professional(bati, USAGES)
    assert len(kept) == 1
    assert kept.iloc[0]["usage_1"] == "Commercial et services"


def test_clip_to_polygon_uses_representative_point() -> None:
    bati = gpd.GeoDataFrame(
        [_bati("Industriel", 900_000), _bati("Industriel", 950_000)], crs=L93
    )
    mask = gpd.GeoDataFrame(geometry=[box(899_900, 6_399_900, 900_100, 6_400_100)], crs=L93)
    inside = processing.clip_to_polygon(bati, mask)
    assert len(inside) == 1
    assert inside.iloc[0]["cleabs"] == "b-900000"


def test_count_and_status_flags_vacant_candidate() -> None:
    bati = gpd.GeoDataFrame(
        [_bati("Industriel", 900_000), _bati("Industriel", 900_500)], crs=L93
    )
    # One active establishment ~5 m from the first building, none near the second.
    sirene = gpd.GeoDataFrame(
        {"siret": ["111"]}, geometry=[Point(900_025, 6_400_010)], crs=L93
    )
    counted = processing.count_etablissements(bati, sirene, buffer_m=15.0)
    result = processing.build_result(counted, "01053", "Bourg-en-Bresse")

    by_id = result.set_index("id_bati")
    assert by_id.loc["b-900000", "statut_occupation"] == "OCCUPE"
    assert by_id.loc["b-900500", "statut_occupation"] == "VACANT_CANDIDAT"
    assert set(processing.OUTPUT_COLS) <= set(result.columns)
    assert (result["surface_bati_m2"] > 0).all()


def test_summarize_returns_counts() -> None:
    bati = gpd.GeoDataFrame([_bati("Industriel", 900_000)], crs=L93)
    counted = processing.count_etablissements(bati, gpd.GeoDataFrame({"siret": []}, geometry=[], crs=L93), 15.0)
    result = processing.build_result(counted, "01053", "Test")
    stats = processing.summarize(result)
    assert isinstance(stats, dict)
    assert stats  # non-empty summary
