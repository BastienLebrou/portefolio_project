"""core.aoi offline tests — resolution that needs no network."""

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from core.aoi import resolve_aoi


def test_resolve_bbox() -> None:
    a = resolve_aoi((4.0, 44.0, 5.0, 45.0))
    assert a.kind == "bbox"
    assert a.aoi_id == "bbox-4.0000_44.0000_5.0000_45.0000"
    assert a.bbox_wgs84 == (4.0, 44.0, 5.0, 45.0)


def test_resolve_gdf() -> None:
    gdf = gpd.GeoDataFrame(geometry=[box(4, 44, 5, 45)], crs="EPSG:4326")
    a = resolve_aoi(gdf)
    assert a.kind == "gdf"
    assert a.geom.area > 0


def test_resolve_file(tmp_path: Path) -> None:
    p = tmp_path / "aoi.parquet"
    gpd.GeoDataFrame(geometry=[box(4, 44, 5, 45)], crs="EPSG:4326").to_parquet(p)
    a = resolve_aoi(p)
    assert a.kind == "file"
    assert a.aoi_id == "file-aoi"


def test_resolve_passthrough() -> None:
    a = resolve_aoi((4.0, 44.0, 5.0, 45.0))
    assert resolve_aoi(a) is a


def test_to_l93_is_metric() -> None:
    a = resolve_aoi((4.0, 44.0, 5.0, 45.0))
    assert abs(a.to_l93().bounds[0]) > 1000  # metres, not degrees


def test_resolve_bad_input() -> None:
    with pytest.raises(ValueError):
        resolve_aoi(42)


def test_communes_in_aoi_filters_to_intersecting(monkeypatch) -> None:
    """Communes are derived from the AOI: right département looked up, non-touching dropped."""
    import core.aoi as aoi_mod

    # geo.api point lookups all resolve to département 07.
    dept07 = [{"codeDepartement": "07"}]
    monkeypatch.setattr(aoi_mod, "_get_json", lambda url, params, timeout: dept07)

    inside = box(4.0, 44.0, 4.5, 44.5)  # overlaps the AOI below
    outside = box(6.0, 46.0, 6.5, 46.5)  # far away
    communes = gpd.GeoDataFrame(
        {"code": ["07001", "07999"], "nom": ["In", "Out"]},
        geometry=[inside, outside],
        crs="EPSG:4326",
    )
    monkeypatch.setattr(aoi_mod, "fetch_communes", lambda dept, timeout=60: communes)

    got = aoi_mod.communes_in_aoi((4.1, 44.1, 4.3, 44.3))
    assert got["code"].tolist() == ["07001"]
