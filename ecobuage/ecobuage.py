"""Écobuage (brûlage dirigé) — scoring multicritère d'aptitude.

Transforme une pile de rasters-critères *alignés* (même grille, même CRS) en une carte
d'aptitude 0-100 et un zonage 3 classes : prioritaire / à étudier / à exclure.

L'ingestion satellite et les indices (NDVI, NBR, sécheresse, tendance) vivent déjà dans
VégéVigie — ce module ne fait QUE l'étape de scoring : il consomme des critères déjà
normalisés, pas des scènes brutes. Voir README.md pour les critères, pondérations et
seuils. Pur NumPy + un export GeoTIFF (rasterio, déjà une dépendance).
"""

from __future__ import annotations

import numpy as np


def rescale(a: np.ndarray, lo: float, hi: float, invert: bool = False) -> np.ndarray:
    """Normalise un critère en 0..1 (clippé). ``invert=True`` -> plus bas = mieux."""
    s = np.clip((a - lo) / (hi - lo), 0.0, 1.0)
    return 1.0 - s if invert else s


def band(a: np.ndarray, lo: float, hi: float, ramp: float) -> np.ndarray:
    """1 dans [lo, hi], rampe linéaire vers 0 sur ``ramp`` de chaque côté.

    Pour la pente : la plage exploitable est une bande (trop plat = inutile, trop raide =
    infaisable), pas une fonction monotone.
    """
    below = rescale(a, lo - ramp, lo)
    above = rescale(a, hi, hi + ramp, invert=True)
    return np.minimum(below, above)


def aptitude(
    criteria: list[tuple[np.ndarray, float]], exclusions: np.ndarray | None = None
) -> np.ndarray:
    """Somme pondérée de critères 0..1 -> aptitude 0..100.

    ``criteria`` : liste de ``(raster_0..1, poids)``. ``exclusions`` : masque booléen des
    cellules à exclure d'office (proximité habitat, Natura 2000...) -> score forcé à 0.
    """
    total_w = sum(w for _, w in criteria)
    if total_w <= 0:
        raise ValueError("La somme des poids doit être > 0.")
    score = sum(c * w for c, w in criteria) / total_w * 100.0
    if exclusions is not None:
        score = np.where(exclusions, 0.0, score)
    return score


def classify(score: np.ndarray, prioritaire: float = 66.0, etudier: float = 33.0) -> np.ndarray:
    """0 = à exclure, 1 = à étudier, 2 = prioritaire (seuils sur l'aptitude 0-100)."""
    cls = np.zeros(score.shape, dtype="int8")
    cls[score >= etudier] = 1
    cls[score >= prioritaire] = 2
    return cls


def write_geotiff(array: np.ndarray, profile: dict, path: str) -> str:
    """Écrit ``array`` (2D) en GeoTIFF ouvrable dans QGIS/ArcGIS, avec ``profile``
    (crs + transform + shape) hérité d'un raster-critère source (rasterio)."""
    import rasterio

    prof = {**profile, "count": 1, "dtype": array.dtype.name}
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(array, 1)
    return path


if __name__ == "__main__":
    # ponytail: self-check sur 3 cellules synthétiques (favorable / faible / exclue).
    combustible = np.array([[0.9, 0.2, 0.8]])  # biomasse sèche / NDVI-NBR, 0..1
    embrouss = np.array([[0.8, 0.1, 0.7]])  # recolonisation ligneuse, 0..1
    slope_pct = np.array([[25.0, 3.0, 30.0]])  # pente %
    access = np.array([[0.9, 0.5, 0.8]])  # proximité réseau routier, 0..1
    hist = np.array([[0.6, 0.2, 0.6]])  # historique feux (récurrence), 0..1
    excl = np.array([[False, False, True]])  # 3e cellule : à < buffer d'un habitat

    score = aptitude(
        [
            (combustible, 25),
            (embrouss, 25),
            (band(slope_pct, 15, 40, ramp=10), 20),
            (access, 15),
            (hist, 15),
        ],
        exclusions=excl,
    )
    cls = classify(score)
    assert cls[0, 0] == 2, cls  # tout favorable, non exclu -> prioritaire
    assert cls[0, 1] == 0, cls  # végétation faible + quasi plat -> exclure
    assert cls[0, 2] == 0, cls  # exclu malgré de bons critères
    print("aptitude:", score.round(1), "| classes:", cls.tolist())
    print("ok")
