"""Zones humides potentielles « à la volée » — à partir du relief (MNT).

POURQUOI. Les zones humides sont un enjeu écologique fort, mais la donnée officielle est
lacunaire. On peut en estimer le *potentiel* depuis la topographie seule : l'eau s'accumule là
où le terrain est **plat** ET **en creux** (fonds de vallon, cuvettes). C'est l'idée du
Topographic Wetness Index, ici en version légère et sans dépendance lourde.

Deux ingrédients, combinés en un score 0-1 :
- **platitude** : 1 quand la pente est faible (l'eau ne s'écoule pas) ;
- **creux** : 1 quand la cellule est plus basse que son voisinage (l'eau converge vers elle).

POUR PLUS TARD : un vrai NDWI (vert/NIR) affinerait avec l'humidité observée par satellite —
il faut d'abord ajouter la bande verte (B03) au datacube ; la topographie suffit en v1.
"""

from __future__ import annotations

import numpy as np


def ndwi(green: np.ndarray, nir: np.ndarray) -> np.ndarray:
    """NDWI de McFeeters (vert − NIR)/(vert + NIR) : élevé sur l'eau libre / sols humides."""
    green = np.asarray(green, dtype="float64")
    nir = np.asarray(nir, dtype="float64")
    denom = green + nir
    return np.divide(green - nir, denom, out=np.zeros_like(denom), where=denom != 0)


def topographic_wetness(
    dem: np.ndarray,
    cellsize: float,
    slope_ref: float = 0.05,
    depression_ref: float = 3.0,
    neighborhood: int = 9,
) -> np.ndarray:
    """Potentiel de zone humide 0-1 depuis le MNT (plat × en creux). NaN → 0.

    ``slope_ref`` : pente (rise/run) au-delà de laquelle on considère « pas plat » (5 % par
    défaut). ``depression_ref`` : dénivelé (m) sous le voisinage pour un creux « franc ».
    ``neighborhood`` : taille de la fenêtre (pixels) pour estimer l'altitude alentour.
    """
    from scipy.ndimage import uniform_filter

    dem = np.asarray(dem, dtype="float64")
    finite = np.isfinite(dem)
    filled = np.where(finite, dem, np.nanmean(dem[finite]) if finite.any() else 0.0)

    # Platitude : pente faible → proche de 1.
    gy, gx = np.gradient(filled, cellsize)
    slope = np.hypot(gx, gy)
    flatness = np.clip(1.0 - slope / slope_ref, 0.0, 1.0)

    # Creux : de combien la cellule est-elle SOUS la moyenne de son voisinage.
    smoothed = uniform_filter(filled, size=neighborhood, mode="nearest")
    depression = np.clip((smoothed - filled) / depression_ref, 0.0, 1.0)

    # Il faut être plat ET en creux pour retenir l'eau → moyenne géométrique.
    wetness = np.sqrt(flatness * depression)
    wetness[~finite] = 0.0
    return wetness
