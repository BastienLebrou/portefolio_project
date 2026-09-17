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
    # to_crs(L93) : on reprojette en Lambert-93 (mètres) car on va calculer des SURFACES —
    # impossible de le faire correctement en degrés WGS84 (un degré ne fait pas la même
    # distance selon la latitude).
    hx = hexagons.to_crs(L93)
    if reservoirs is None or reservoirs.empty:
        # Pas de réservoir à comparer = aucun enjeu détecté nulle part : on renvoie 0.0
        # pour chaque hexagone plutôt que de planter ou renvoyer une valeur manquante.
        return pd.Series(0.0, index=hexagons["hex_id"], name="enjeu")
    # union_all() fusionne tous les réservoirs en une seule forme
    res_u = reservoirs.to_crs(L93).union_all()
    # intersection(res_u).area = la surface commune entre chaque hexagone et les
    # réservoirs ; on la divise par la surface totale de l'hexagone pour obtenir une
    # FRACTION (0 = aucun recouvrement, 1 = hexagone entièrement dans un réservoir).
    inter = hx.geometry.intersection(res_u).area
    frac = (inter / hx.geometry.area).clip(0.0, 1.0)
    return pd.Series(frac.to_numpy(), index=hexagons["hex_id"], name="enjeu")


def proximity(
    hexagons: gpd.GeoDataFrame, features: gpd.GeoDataFrame, max_m: float, name: str
) -> pd.Series:
    """Proximity (0-1) of each hexagon centroid to the nearest feature (0 m = 1, ≥ max = 0)."""
    hx = hexagons.to_crs(L93)
    if features is None or features.empty:
        return pd.Series(0.0, index=hexagons["hex_id"], name=name)
    target = features.to_crs(L93).union_all()
    # distance() donne la distance (en mètres) du centre de chaque hexagone à l'objet le
    # plus proche. On transforme cette distance en un score de "proximité" entre 0 et 1 :
    # à 0 m -> 1.0 (collé au réservoir/corridor), à max_m ou plus -> 0.0 (trop loin pour
    # compter), et une décroissance linéaire entre les deux.
    dist = hx.geometry.centroid.distance(target)
    prox = (1.0 - dist / max_m).clip(0.0, 1.0)
    return pd.Series(prox.to_numpy(), index=hexagons["hex_id"], name=name)


def reservoir_proximity(
    hexagons: gpd.GeoDataFrame, reservoirs: gpd.GeoDataFrame, corridor_max_m: float = 2000.0
) -> pd.Series:
    """Connectivité proxy: proximity to the nearest reservoir (used when no TVB is available)."""
    return proximity(hexagons, reservoirs, corridor_max_m, "connectivite")


def corridor_proximity(
    hexagons: gpd.GeoDataFrame, corridors: gpd.GeoDataFrame, corridor_max_m: float = 2000.0
) -> pd.Series:
    """Connectivité (real): proximity to the nearest TVB corridor (SRCE/SRADDET)."""
    return proximity(hexagons, corridors, corridor_max_m, "connectivite")
