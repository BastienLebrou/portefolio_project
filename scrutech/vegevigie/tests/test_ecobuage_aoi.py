"""AOI-only écobuage orchestrator — synthetic DEM + mocked BD TOPO, no network."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, box

from vegevigie.ecobuage_aoi import build_aptitude_from_aoi

L93 = "EPSG:2154"

# A small AOI in Lambert-93 metres.
AOI = box(900_000, 6_400_000, 900_500, 6_400_500)


def _write_dem(path, crs=None) -> None:
    # 75 m DEM over the AOI + margin, elevation ramping in x → a constant, non-zero slope.
    res = 75.0
    minx, miny = 899_000.0, 6_399_000.0
    w = h = 40
    xs = np.arange(w) * res * 0.20  # 20 % slope in x
    dem = np.tile(xs, (h, 1)).astype("float32")
    transform = from_origin(minx, miny + h * res, res, res)
    prof = {
        "driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": "float32",
        "transform": transform, "nodata": -99999.0,
    }
    if crs is not None:
        prof["crs"] = crs
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(dem, 1)


def test_build_aptitude_from_aoi_writes_rasters(tmp_path, monkeypatch) -> None:
    import core.sources as sources

    # A road crossing the AOI, and one building near a corner.
    road = gpd.GeoDataFrame(
        geometry=[LineString([(900_000, 6_400_250), (900_500, 6_400_250)])], crs=L93
    )
    bati = gpd.GeoDataFrame(geometry=[box(900_010, 6_400_010, 900_030, 6_400_030)], crs=L93)
    monkeypatch.setattr(sources, "fetch_roads", lambda aoi, **k: road)
    monkeypatch.setattr(sources, "fetch_buildings", lambda aoi, **k: bati)

    dem = tmp_path / "mnt.tif"
    _write_dem(dem, crs=None)  # CRS missing on purpose — engine assumes L93

    aoi = gpd.GeoDataFrame(geometry=[AOI], crs=L93)
    apt, cls, info = build_aptitude_from_aoi(aoi, dem, tmp_path / "out", resolution=50.0)

    assert apt.exists() and cls.exists()
    with rasterio.open(cls) as ds:
        arr = ds.read(1)
        assert ds.crs.to_epsg() == 2154
        assert arr.shape == (10, 10)  # 500 m / 50 m
        assert set(np.unique(arr)).issubset({0, 1, 2})
    # No VegeVigie rasters passed → only terrain + access criteria used.
    assert info["criteria"] == ["slope", "access"]
    # The building buffer (100 m) must have excluded some cells (class 0).
    assert info["n_a_exclure"] > 0


def test_veg_rasters_add_criteria(tmp_path, monkeypatch) -> None:
    import core.sources as sources

    monkeypatch.setattr(sources, "fetch_roads", lambda aoi, **k: gpd.GeoDataFrame(
        geometry=[LineString([(900_000, 6_400_250), (900_500, 6_400_250)])], crs=L93))
    monkeypatch.setattr(sources, "fetch_buildings", lambda aoi, **k: gpd.GeoDataFrame(
        geometry=[], crs=L93))

    dem = tmp_path / "mnt.tif"
    _write_dem(dem, crs=L93)
    # A tiny VegeVigie-like trend raster covering the AOI.
    trend = tmp_path / "trend.tif"
    with rasterio.open(
        trend, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32",
        crs=L93, transform=from_origin(900_000, 6_400_500, 50, 50),
    ) as dst:
        dst.write(np.full((10, 10), 0.008, dtype="float32"), 1)

    aoi = gpd.GeoDataFrame(geometry=[AOI], crs=L93)
    _, _, info = build_aptitude_from_aoi(
        aoi, dem, tmp_path / "out", resolution=50.0, veg_trend_tif=trend
    )
    assert "embroussaillement" in info["criteria"]
