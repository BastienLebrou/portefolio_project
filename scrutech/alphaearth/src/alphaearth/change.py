"""Year-over-year change from AlphaEarth embeddings — cosine distance.

CE QUE ÇA FAIT : compare les embeddings d'une même AOI entre deux années et marque
les pixels dont la signature a vraiment changé.

POURQUOI (rupture vs v1) : la v1 comparait des indices spectraux (NDVI avant/après),
sensibles aux nuages, à la saison et à l'atmosphère. AlphaEarth a déjà absorbé ces
variations dans l'embedding → la distance cosine entre deux vecteurs 64-D mesure un
**vrai changement de surface**, pas un artefact atmosphérique.

VULGARISATION : au lieu de comparer deux photos prises par temps différent, on compare
deux « empreintes » qui ignorent déjà la météo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from alphaearth._columns import EMB_COLS


def cosine_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine distance ``1 - cos(a, b)`` between two ``(N, 64)`` arrays (0 = identical)."""
    # Version numpy (calcul en Python/local) de la même formule que côté Earth Engine :
    # on normalise chaque vecteur (le divise par sa propre longueur) pour ne garder que
    # sa direction, puis le produit scalaire des vecteurs normalisés donne le cosinus.
    # "+ 1e-12" est un tout petit nombre ajouté pour ne jamais diviser par zéro si un
    # vecteur est nul (norme = 0). `axis=1` = calcule le long de chaque ligne (chaque
    # pixel), pas sur tout le tableau d'un coup ; `keepdims=True` garde la forme en
    # colonne pour que la division ligne par ligne fonctionne correctement.
    an = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    bn = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return 1.0 - np.sum(an * bn, axis=1)


def flag_by_percentile(distances: np.ndarray, percentile: float = 95.0) -> tuple[np.ndarray, float]:
    """Flag the top ``distances`` above the given percentile. Returns (changed_mask, threshold).

    Used by the AOI change pipeline where the distance is computed server-side (already
    pixel-aligned), so no row merge is needed — just the threshold.
    """
    if distances.size == 0:
        return np.zeros(0, dtype=bool), 0.0
    # Le 95e percentile est la valeur en dessous de laquelle se trouvent 95 % des
    # distances : ne garder que ce qui dépasse ce seuil revient à isoler les 5 % de
    # pixels dont le changement est le plus marqué, plutôt que de fixer un seuil "en dur"
    # qui dépendrait de la zone étudiée.
    threshold = float(np.percentile(distances, percentile))
    return distances > threshold, threshold


def detect_change(
    t1: pd.DataFrame,
    t2: pd.DataFrame,
    threshold_percentile: float = 95.0,
    key: str = "pixel_id",
) -> pd.DataFrame:
    """Per-pixel change between two years of embeddings, aligned on ``key``.

    ``t1`` / ``t2`` carry the 64 ``EMB_COLS`` (+ ``key``). Returns a frame with
    ``change_distance`` and ``changed`` (distance above the given percentile).
    """
    # merge() est l'équivalent pandas d'une jointure SQL : on associe chaque pixel de t1
    # à SON pixel correspondant dans t2 via la clé `key` (ex: pixel_id). `suffixes`
    # renomme les colonnes en double ("A00" devient "A00_t1" et "A00_t2") pour ne pas
    # les confondre une fois fusionnées dans le même tableau.
    merged = t1[[key, *EMB_COLS]].merge(t2[[key, *EMB_COLS]], on=key, suffixes=("_t1", "_t2"))
    a = merged[[f"{c}_t1" for c in EMB_COLS]].to_numpy(dtype=float)
    b = merged[[f"{c}_t2" for c in EMB_COLS]].to_numpy(dtype=float)
    dist = cosine_distance(a, b)
    threshold = float(np.percentile(dist, threshold_percentile)) if dist.size else 0.0
    out = merged[[key]].copy()
    out["change_distance"] = dist
    out["changed"] = dist > threshold
    return out
