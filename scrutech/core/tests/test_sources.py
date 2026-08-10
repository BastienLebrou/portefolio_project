"""core.sources offline tests — WFS pagination, 2D flatten, AOI clip (requests mocked)."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from core import sources


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def _feature(x: float, y: float, nature: str = "Forêt fermée de feuillus") -> dict:
    # A tiny 3D polygon around (x, y) in L93 metres — Z must be dropped by _force_2d.
    ring = [[x, y, 10.0], [x + 50, y, 10.0], [x + 50, y + 50, 10.0], [x, y + 50, 10.0], [x, y, 10.0]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"cleabs": f"b-{x:.0f}", "nature": nature},
    }


def test_fetch_bdtopo_paginates_flattens_and_clips(monkeypatch) -> None:
    # AOI = a 100 m box in L93 near Ardèche; only the feature inside it must survive the clip.
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.601, 44.501)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    minx, miny, _, _ = resolve_aoi(aoi).to_l93().bounds

    inside = _feature(minx + 5, miny + 5)  # inside the AOI
    outside = _feature(minx + 5_000, miny + 5_000)  # far away → clipped out

    # First page returns PAGE_SIZE-1 features → loop stops after one call (got < page size).
    monkeypatch.setattr(sources, "WFS_PAGE_SIZE", 10)
    calls = {"n": 0}

    def fake_get(url, params, timeout):
        calls["n"] += 1
        return _FakeResp({"features": [inside, outside]})

    monkeypatch.setattr(sources.requests, "get", fake_get)

    gdf = sources.fetch_bdtopo(aoi, "BDTOPO_V3:zone_de_vegetation", ["cleabs", "nature"])
    assert calls["n"] == 1
    assert gdf.crs.to_epsg() == 2154
    assert len(gdf) == 1  # only the inside feature survived the clip
    assert not gdf.geometry.iloc[0].has_z  # 3D flattened to 2D


def test_fetch_forest_keeps_only_forest_natures(monkeypatch) -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    c = resolve_aoi(aoi).to_l93().centroid  # anchor inside the (rotated) AOI polygon
    feats = [
        _feature(c.x - 100, c.y, "Forêt fermée de conifères"),
        _feature(c.x + 100, c.y, "Vigne"),  # not forest → dropped
        _feature(c.x, c.y + 100, "Bois"),
    ]
    monkeypatch.setattr(sources.requests, "get", lambda url, params, timeout: _FakeResp({"features": feats}))

    forest = sources.fetch_forest(aoi)
    assert set(forest["nature"]) == {"Forêt fermée de conifères", "Bois"}
