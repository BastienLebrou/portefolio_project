"""Cross the biotrame axes into a priority score — the ecological-need scoreboard.

Score = **geometric mean of the available axes** (each 0-1), ×100. The geometric mean is
deliberate: a hexagon must score on *all* axes to rank high (high ecological stake AND
degrading AND connected). A zero on any axis → zero priority, and the mean stays comparable
whatever the number of axes present (so runs with/without the satellite axis are on the
same 0-100 scale).
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from biotrame.aggregate import reservoir_overlap, reservoir_proximity

# Class thresholds on the 0-100 score.
PRIORITAIRE, A_ETUDIER = 66.0, 33.0


def priority_score(axes: dict[str, np.ndarray]) -> np.ndarray:
    """Geometric mean (×100) of the non-None axes, each clipped to 0-1."""
    present = [
        np.clip(np.asarray(a, dtype=float), 0.0, 1.0) for a in axes.values() if a is not None
    ]
    if not present:
        raise ValueError("At least one axis is required to score.")
    gmean = np.prod(present, axis=0) ** (1.0 / len(present))
    return gmean * 100.0


def classify(score: np.ndarray) -> np.ndarray:
    """0 = secondaire, 1 = à étudier, 2 = prioritaire (thresholds on the 0-100 score)."""
    cls = np.zeros(np.shape(score), dtype="int8")
    cls[score >= A_ETUDIER] = 1
    cls[score >= PRIORITAIRE] = 2
    return cls


def score_mesh(
    hexagons: gpd.GeoDataFrame,
    reservoirs: gpd.GeoDataFrame,
    degradation: pd.Series | None = None,
    corridor_max_m: float = 2000.0,
) -> gpd.GeoDataFrame:
    """Assemble the scored mesh: enjeu + connectivité (+ optional dégradation) → score + classe.

    ``degradation`` (if given) is a 0-1 Series indexed by ``hex_id`` computed raster-side by
    the orchestrator. Returns the hexagons with the per-axis columns, ``score`` and ``classe``.
    """
    enjeu = reservoir_overlap(hexagons, reservoirs)
    connect = reservoir_proximity(hexagons, reservoirs, corridor_max_m)

    out = hexagons.copy()
    out["enjeu"] = enjeu.to_numpy()
    out["connectivite"] = connect.to_numpy()
    axes: dict[str, np.ndarray] = {
        "enjeu": out["enjeu"].to_numpy(),
        "connectivite": out["connectivite"].to_numpy(),
    }
    if degradation is not None:
        out["degradation"] = degradation.reindex(out["hex_id"]).to_numpy()
        axes["degradation"] = np.nan_to_num(out["degradation"].to_numpy(), nan=0.0)

    out["score"] = priority_score(axes)
    out["classe"] = classify(out["score"].to_numpy())
    return out
