"""AOI-only biotrame orchestrator — mocked reservoirs + synthetic trend raster, no network."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

from vegevigie.biotrame_aoi import build_priority_mesh_from_aoi

AOI = box(4.60, 44.50, 4.70, 44.60)  # WGS84


def test_priority_mesh_writes_outputs_and_axes(tmp_path, monkeypatch) -> None:
    import core.sources as sources

    # A reservoir covering the western half of the AOI (mock the WFS fetch).
    reservoirs = gpd.GeoDataFrame(
        {"kind": ["natura2000_sic"], "nom_site": ["X"]},
        geometry=[box(4.60, 44.50, 4.65, 44.60)],
        crs="EPSG:4326",
    ).to_crs("EPSG:2154")
    monkeypatch.setattr(sources, "fetch_biodiversity_reservoirs", lambda aoi, **k: reservoirs)

    aoi = gpd.GeoDataFrame(geometry=[AOI], crs="EPSG:4326")
    parquet, geojson, info = build_priority_mesh_from_aoi(aoi, tmp_path / "out", resolution=8)

    assert parquet.exists() and geojson.exists()
    assert info["n_hexagons"] > 0
    assert info["axes"] == ["enjeu", "connectivite"]  # no trend raster → no degradation axis
    scored = gpd.read_parquet(parquet)
    assert {"enjeu", "connectivite", "score", "classe"} <= set(scored.columns)


def test_trend_raster_adds_degradation_axis(tmp_path, monkeypatch) -> None:
    import core.sources as sources

    monkeypatch.setattr(
        sources,
        "fetch_biodiversity_reservoirs",
        lambda aoi, **k: gpd.GeoDataFrame(
            {"kind": ["znieff1"], "nom_site": ["Y"]},
            geometry=[box(4.60, 44.50, 4.65, 44.60)],
            crs="EPSG:4326",
        ).to_crs("EPSG:2154"),
    )

    # A browning trend raster (negative Sen slope) over the AOI in L93.
    aoi_l93 = gpd.GeoDataFrame(geometry=[AOI], crs="EPSG:4326").to_crs("EPSG:2154")
    minx, miny, maxx, maxy = aoi_l93.total_bounds
    res = 100.0
    w = int((maxx - minx) / res) + 1
    h = int((maxy - miny) / res) + 1
    trend = tmp_path / "trend.tif"
    with rasterio.open(
        trend,
        "w",
        driver="GTiff",
        width=w,
        height=h,
        count=1,
        dtype="float32",
        crs="EPSG:2154",
        transform=from_origin(minx, maxy, res, res),
        nodata=-9999.0,
    ) as dst:
        dst.write(np.full((h, w), -0.02, dtype="float32"), 1)  # browning everywhere

    aoi = gpd.GeoDataFrame(geometry=[AOI], crs="EPSG:4326")
    _, _, info = build_priority_mesh_from_aoi(
        aoi, tmp_path / "out", resolution=8, veg_trend_tif=trend
    )
    assert "degradation" in info["axes"]


def test_mnt_adds_wetland_enjeu_boost(tmp_path, monkeypatch) -> None:
    import core.sources as sources

    # No reservoirs → enjeu comes only from the wetland boost.
    monkeypatch.setattr(
        sources,
        "fetch_biodiversity_reservoirs",
        lambda aoi, **k: gpd.GeoDataFrame(geometry=[], crs="EPSG:2154"),
    )
    # A DEM over the AOI with a flat low basin (a likely wetland) in the middle.
    aoi_l93 = gpd.GeoDataFrame(geometry=[AOI], crs="EPSG:4326").to_crs("EPSG:2154")
    minx, miny, maxx, maxy = aoi_l93.total_bounds
    res = 75.0
    w = int((maxx - minx) / res) + 8
    h = int((maxy - miny) / res) + 8
    yy, xx = np.mgrid[0:h, 0:w]
    dem = (xx * 1.5).astype("float32")
    dem[h // 3 : 2 * h // 3, w // 3 : 2 * w // 3] = float(dem.min()) - 5.0
    mnt = tmp_path / "mnt.tif"
    with rasterio.open(
        mnt,
        "w",
        driver="GTiff",
        width=w,
        height=h,
        count=1,
        dtype="float32",
        crs="EPSG:2154",
        transform=from_origin(minx - 3 * res, maxy + 3 * res, res, res),
    ) as dst:
        dst.write(dem, 1)

    aoi = gpd.GeoDataFrame(geometry=[AOI], crs="EPSG:4326")
    _, _, info = build_priority_mesh_from_aoi(aoi, tmp_path / "out", resolution=8, mnt_path=mnt)
    assert info["enjeu_boost"] == "zones_humides_mnt"
    scored = gpd.read_parquet(tmp_path / "out" / "biotrame_priority.parquet")
    assert float(scored["enjeu"].max()) > 0.0  # the basin lifted some hexagons' enjeu
