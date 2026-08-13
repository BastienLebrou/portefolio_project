"""biotrame.mesh tests — H3 tessellation of an AOI, no network."""

from __future__ import annotations

import geopandas as gpd
from biotrame.mesh import hex_grid
from shapely.geometry import box


def test_hex_grid_covers_aoi() -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    grid = hex_grid(aoi, resolution=8)
    assert len(grid) > 10
    assert grid.crs.to_epsg() == 4326
    assert grid.geometry.is_valid.all()
    assert grid["hex_id"].is_unique
    # The hexagons blanket the AOI: their union contains most of the box.
    covered = grid.union_all()
    assert covered.intersection(aoi.geometry.iloc[0]).area / aoi.geometry.iloc[0].area > 0.95


def test_coarser_resolution_gives_fewer_cells() -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    assert len(hex_grid(aoi, resolution=7)) < len(hex_grid(aoi, resolution=9))


def test_tiny_aoi_falls_back_to_centroid_cell() -> None:
    # A box far smaller than an r8 hexagon catches no cell centre → centroid fallback.
    aoi = gpd.GeoDataFrame(geometry=[box(4.600, 44.500, 4.6005, 44.5005)], crs="EPSG:4326")
    grid = hex_grid(aoi, resolution=8)
    assert len(grid) == 1
