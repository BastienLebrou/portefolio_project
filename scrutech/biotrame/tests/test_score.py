"""biotrame scoring tests — axes crossing on synthetic hexagons + a reservoir, no network."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from biotrame.mesh import hex_grid
from biotrame.score import classify, priority_score, score_mesh
from shapely.geometry import box


def test_priority_score_is_geometric_mean() -> None:
    # A zero on any axis → zero; all-ones → 100.
    axes = {"a": np.array([1.0, 0.0, 0.5]), "b": np.array([1.0, 1.0, 0.5])}
    got = priority_score(axes)
    assert got[0] == 100.0
    assert got[1] == 0.0
    assert np.isclose(got[2], 50.0)  # sqrt(0.25) * 100


def test_classify_thresholds() -> None:
    cls = classify(np.array([10.0, 40.0, 80.0]))
    assert cls.tolist() == [0, 1, 2]


def test_score_mesh_crosses_reservoir_and_degradation() -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.60, 44.50, 4.70, 44.60)], crs="EPSG:4326")
    grid = hex_grid(aoi, resolution=8)
    # A reservoir covering the western half of the AOI.
    reservoirs = gpd.GeoDataFrame(geometry=[box(4.60, 44.50, 4.65, 44.60)], crs="EPSG:4326")

    scored = score_mesh(grid, reservoirs)
    assert {"enjeu", "connectivite", "score", "classe"} <= set(scored.columns)
    assert (scored["enjeu"] > 0).any()  # some hexagons overlap the reservoir
    assert scored["enjeu"].between(0, 1).all()
    assert scored["score"].between(0, 100).all()
    assert set(np.unique(scored["classe"])).issubset({0, 1, 2})

    # With a degradation axis, the score reflects all three (geometric mean over 3 axes).
    degr = pd.Series(1.0, index=grid["hex_id"])
    scored3 = score_mesh(grid, reservoirs, degradation=degr)
    assert "degradation" in scored3.columns


def test_corridors_drive_connectivity_when_present() -> None:
    from shapely.geometry import LineString

    aoi = gpd.GeoDataFrame(geometry=[box(4.60, 44.50, 4.70, 44.60)], crs="EPSG:4326")
    grid = hex_grid(aoi, resolution=8)
    reservoirs = gpd.GeoDataFrame(geometry=[box(4.60, 44.50, 4.62, 44.60)], crs="EPSG:4326")
    # A corridor line crossing the eastern side, far from the reservoir.
    corridors = gpd.GeoDataFrame(
        geometry=[LineString([(4.68, 44.50), (4.68, 44.60)])], crs="EPSG:4326"
    )
    proxy = score_mesh(grid, reservoirs)
    real = score_mesh(grid, reservoirs, corridors=corridors)
    # .equals() compare deux Series élément par élément (contrairement à `==` qui
    # renverrait une série de booléens à agréger soi-même) : ici on vérifie qu'elles ne
    # sont PAS identiques, preuve que passer des corridors change bien le résultat.
    # The connectivity field must differ when real corridors drive it.
    assert not proxy["connectivite"].equals(real["connectivite"])
