"""Per-hexagon aggregation of the biotrame axes — pure vector maths (metric CRS).

Two of the three biotrame axes come from the existing cartography (reservoirs):

- **enjeu** : fraction of the hexagon covered by a biodiversity reservoir (Natura 2000 /
  ZNIEFF …) — how much this cell *matters* ecologically;
- **connectivité** : proximity of the hexagon to a reservoir, within a corridor distance —
  a proxy for "is this cell a link in the network" while real TVB corridors are wired in.

All area/distance maths run in Lambert-93. The third axis (dégradation, from satellite) is
computed raster-side by the orchestrator and merged in later.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from core.constants import L93


def reservoir_overlap(hexagons: gpd.GeoDataFrame, reservoirs: gpd.GeoDataFrame) -> pd.Series:
    """Fraction (0-1) of each hexagon's area covered by a reservoir, indexed by ``hex_id``."""
    hx = hexagons.to_crs(L93)
    if reservoirs is None or reservoirs.empty:
        return pd.Series(0.0, index=hexagons["hex_id"], name="enjeu")
    res_u = reservoirs.to_crs(L93).union_all()
    inter = hx.geometry.intersection(res_u).area
    frac = (inter / hx.geometry.area).clip(0.0, 1.0)
    return pd.Series(frac.to_numpy(), index=hexagons["hex_id"], name="enjeu")


def reservoir_proximity(
    hexagons: gpd.GeoDataFrame, reservoirs: gpd.GeoDataFrame, corridor_max_m: float = 2000.0
) -> pd.Series:
    """Proximity (0-1) of each hexagon to the nearest reservoir (0 m = 1, ≥ max = 0)."""
    hx = hexagons.to_crs(L93)
    if reservoirs is None or reservoirs.empty:
        return pd.Series(0.0, index=hexagons["hex_id"], name="connectivite")
    res_u = reservoirs.to_crs(L93).union_all()
    dist = hx.geometry.centroid.distance(res_u)
    prox = (1.0 - dist / corridor_max_m).clip(0.0, 1.0)
    return pd.Series(prox.to_numpy(), index=hexagons["hex_id"], name="connectivite")
