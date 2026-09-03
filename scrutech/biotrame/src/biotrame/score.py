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

from biotrame.aggregate import corridor_proximity, reservoir_overlap, reservoir_proximity

# Class thresholds on the 0-100 score.
PRIORITAIRE, A_ETUDIER = 66.0, 33.0


def priority_score(axes: dict[str, np.ndarray]) -> np.ndarray:
    """Geometric mean (×100) of the non-None axes, each clipped to 0-1."""
    # Rappel : la moyenne ARITHMÉTIQUE de [1.0, 0.0] est 0.5 (ça a l'air "moyen"), alors
    # que la moyenne GÉOMÉTRIQUE (racine n-ième du produit) de [1.0, 0.0] est 0 — un seul
    # axe à zéro fait tomber tout le score à zéro. C'est voulu ici (voir docstring du
    # module) : un hexagone doit être bon sur TOUS les axes, pas juste bon en moyenne.
    # clip(0,1) force chaque valeur à rester dans l'intervalle attendu (sécurité contre
    # une valeur aberrante en entrée).
    present = [
        np.clip(np.asarray(a, dtype=float), 0.0, 1.0) for a in axes.values() if a is not None
    ]
    if not present:
        raise ValueError("At least one axis is required to score.")
    # np.prod(present, axis=0) multiplie les tableaux élément par élément (axe 0 = "à
    # travers la liste des axes", donc hexagone par hexagone) ; élever à la puissance
    # 1/n est la formule de la racine n-ième = moyenne géométrique de n valeurs.
    gmean = np.prod(present, axis=0) ** (1.0 / len(present))
    return gmean * 100.0


def classify(score: np.ndarray) -> np.ndarray:
    """0 = secondaire, 1 = à étudier, 2 = prioritaire (thresholds on the 0-100 score)."""
    # On part d'un tableau de zéros (classe "secondaire" par défaut), puis on relève la
    # classe des hexagones qui dépassent chaque seuil. L'ordre compte : le second filtre
    # (>= PRIORITAIRE, seuil plus haut) écrase la classe 1 mise par le premier filtre
    # pour les hexagones qui dépassent les DEUX seuils.
    cls = np.zeros(np.shape(score), dtype="int8")
    cls[score >= A_ETUDIER] = 1
    cls[score >= PRIORITAIRE] = 2
    return cls


def score_mesh(
    hexagons: gpd.GeoDataFrame,
    reservoirs: gpd.GeoDataFrame,
    degradation: pd.Series | None = None,
    corridor_max_m: float = 2000.0,
    corridors: gpd.GeoDataFrame | None = None,
) -> gpd.GeoDataFrame:
    """Assemble the scored mesh: enjeu + connectivité (+ optional dégradation) → score + classe.

    ``degradation`` (if given) is a 0-1 Series indexed by ``hex_id`` computed raster-side by
    the orchestrator. ``corridors`` (real TVB) drive the connectivité axis when provided;
    otherwise it falls back to proximity-to-reservoir. Returns the hexagons with the per-axis
    columns, ``score`` and ``classe``.
    """
    enjeu = reservoir_overlap(hexagons, reservoirs)
    if corridors is not None and not corridors.empty:
        connect = corridor_proximity(hexagons, corridors, corridor_max_m)
    else:
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
