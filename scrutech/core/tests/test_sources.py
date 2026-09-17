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
    ring = [[x, y, 1.0], [x + 50, y, 1.0], [x + 50, y + 50, 1.0], [x, y + 50, 1.0], [x, y, 1.0]]
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
    monkeypatch.setattr(
        sources.requests, "get", lambda url, params, timeout: _FakeResp({"features": feats})
    )

    forest = sources.fetch_forest(aoi)
    assert set(forest["nature"]) == {"Forêt fermée de conifères", "Bois"}


def test_fetch_biodiversity_reservoirs_combines_kinds(monkeypatch) -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    c = resolve_aoi(aoi).to_l93().centroid

    def _site(name: str) -> dict:
        ring = [[c.x, c.y], [c.x + 80, c.y], [c.x + 80, c.y + 80], [c.x, c.y + 80], [c.x, c.y]]
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"nom_site": name},
        }

    monkeypatch.setattr(
        sources.requests,
        "get",
        lambda url, params, timeout: _FakeResp({"features": [_site("Site X")]}),
    )

    gdf = sources.fetch_biodiversity_reservoirs(aoi, kinds=("natura2000_sic", "znieff1"))
    assert set(gdf["kind"]) == {"natura2000_sic", "znieff1"}
    assert list(gdf.columns) == ["kind", "nom_site", "geometry"] or "geometry" in gdf.columns
    assert (gdf["nom_site"] == "Site X").all()
    assert gdf.crs.to_epsg() == 2154


def test_fetch_tvb_corridors_rejects_non_http_url() -> None:
    import pytest

    from core import sources

    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    for bad in ("file:///etc/passwd", "ftp://x/y", "/local/path"):
        with pytest.raises(ValueError, match="http"):
            sources.fetch_tvb_corridors(aoi, "ms:corridors", wfs_url=bad)


def test_fetch_mnt_tiles_fills_lidar_gaps_and_caps_size(tmp_path, monkeypatch) -> None:
    import numpy as np
    import pytest
    import rasterio

    def fake_elevation(layer, bbox, width, height, timeout):
        if "LIDAR" in layer:
            arr = np.full((height, width), 400.0, dtype="float32")
            arr[0, :] = np.nan  # LiDAR HD not flown on the first row of each tile
            return arr
        return np.full((height, width), 500.0, dtype="float32")  # RGE ALTI

    monkeypatch.setattr(sources, "_wms_elevation", fake_elevation)
    monkeypatch.setattr(sources, "WMS_TILE_PX", 4)
    aoi = (4.585, 44.553, 4.586, 44.554)  # ~80 x 110 m
    path, info = sources.fetch_mnt(aoi, tmp_path / "mnt.tif", resolution=10.0)

    with rasterio.open(path) as ds:
        dem = ds.read(1)
        assert ds.crs.to_epsg() == 2154
    assert info["mnt_tiles"] > 1  # the loop really tiled the zone
    assert sorted(np.unique(dem).tolist()) == [400.0, 500.0]  # no hole left
    monkeypatch.setattr(sources, "MNT_MAX_PX", 10)
    with pytest.raises(ValueError, match="trop grande"):
        sources.fetch_mnt(aoi, tmp_path / "big.tif", resolution=10.0)


def test_fetch_ortho_mosaics_rgb_tiles_in_place(tmp_path, monkeypatch) -> None:
    import numpy as np
    import pytest
    import rasterio

    def fake_getmap(layer, bbox, width, height, fmt, timeout):
        assert layer == sources.ORTHO_LAYER and fmt == "image/jpeg"
        tile = np.empty((3, height, width), dtype="uint8")
        tile[0], tile[1], tile[2] = int(bbox[0]) % 251, int(bbox[3]) % 251, 7  # where it is
        return tile

    monkeypatch.setattr(sources, "_getmap", fake_getmap)
    monkeypatch.setattr(sources, "WMS_TILE_PX", 4)
    aoi = (4.585, 44.553, 4.586, 44.554)
    path, info = sources.fetch_ortho(aoi, tmp_path / "ortho.tif", resolution=10.0)

    with rasterio.open(path) as ds:
        image = ds.read()
        assert (ds.count, ds.dtypes[0], ds.crs.to_epsg()) == (3, "uint8", 2154)
        # The top-left pixel of the tile at column 4 carries that tile's own west edge.
        west = ds.transform.c + 4 * ds.transform.a
        assert image[0, 0, 4] == int(west) % 251
    assert info["ortho_tiles"] > 1 and (image[2] == 7).all()
    monkeypatch.setattr(sources, "ORTHO_MAX_PX", 10)
    with pytest.raises(ValueError, match="image aérienne"):
        sources.fetch_ortho(aoi, tmp_path / "big.tif", resolution=10.0)
