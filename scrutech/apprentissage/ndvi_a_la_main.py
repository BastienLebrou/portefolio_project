"""NDVI à la main — tutoriel pas à pas.

Objectif : recoder depuis zéro (sans numpy) l'indice NDVI que le vrai pipeline
ScruTech calcule en une ligne avec numpy/xarray — voir
vegevigie/src/vegevigie/indices.py::compute_ndvi une fois ce fichier compris.

Lance ce fichier directement pour voir les tests passer :
    python ndvi_a_la_main.py
"""

from __future__ import annotations

import math

# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 1 — la formule, sur UN SEUL pixel
# ─────────────────────────────────────────────────────────────────────
#
# Un pixel satellite n'est pas une valeur unique (comme un pixel d'écran
# gris) : c'est un petit vecteur de bandes — rouge, vert, bleu, proche-
# infrarouge (PIR)... Idée physique : une plante en bonne santé (chlorophylle)
# ABSORBE le rouge et RÉFLÉCHIT fort le proche-infrarouge. L'eau et le bâti
# font l'inverse. NDVI mesure cet écart, normalisé entre -1 et 1 :
#
#     NDVI = (PIR − Rouge) / (PIR + Rouge)
#
# Le "/ (PIR + Rouge)" au dénominateur est la normalisation : il ramène
# toujours le résultat entre -1 et 1, peu importe la luminosité de la scène
# (comme diviser par le total pour avoir une proportion, pas une valeur brute).


def ndvi_pixel(rouge: float, pir: float) -> float:
    denominateur = pir + rouge
    if denominateur == 0:
        # pixel "nodata" (noir) : 0/0 est indéfini — on renvoie NaN plutôt
        # que planter ou renvoyer 0 (0 aurait un sens physique, ce n'est pas le cas ici).
        return float("nan")
    return (pir - rouge) / denominateur


# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 2 — une LIGNE de pixels (liste)
# ─────────────────────────────────────────────────────────────────────
# Une image contient des milliers de pixels. Avant de sortir l'artillerie
# numpy, on le fait "à la main" avec une boucle Python classique — pour
# bien voir ce qu'une bibliothèque comme numpy fera ENSUITE à ta place,
# beaucoup plus vite, en une seule ligne vectorisée.


def ndvi_ligne(rouges: list[float], pirs: list[float]) -> list[float]:
    if len(rouges) != len(pirs):
        raise ValueError("rouge et pir doivent avoir la même longueur")
    return [ndvi_pixel(r, p) for r, p in zip(rouges, pirs)]


# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 3 — une IMAGE (grille 2D)
# ─────────────────────────────────────────────────────────────────────
# Une image satellite = une grille de pixels (lignes × colonnes), donc en
# Python pur : une liste de listes. On réutilise ndvi_ligne pour chaque
# ligne plutôt que de dupliquer la boucle — une fonction, une responsabilité.


def ndvi_grille(rouges: list[list[float]], pirs: list[list[float]]) -> list[list[float]]:
    return [ndvi_ligne(r_ligne, p_ligne) for r_ligne, p_ligne in zip(rouges, pirs)]


# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 4 — filtrer les pixels invalides (nuages, ombres, neige...)
# ─────────────────────────────────────────────────────────────────────
# Le satellite voit parfois des nuages ou de la neige : ces pixels polluent
# le NDVI (un nuage blanc peut donner n'importe quelle valeur). Sentinel-2
# fournit une bande "SCL" = une classe par pixel (4=végétation, 8/9=nuage...).
# Règle : on garde seulement les classes "au sol" (4, 5, 6, 7).
#
# Point d'architecture : cette fonction ne touche PAS au calcul du NDVI —
# elle est écrite et testée séparément, puis combinée. Comme séparer, en
# SIG, la requête attributaire (quelles entités garder) du calcul de champ.

CLASSES_VALIDES = {4, 5, 6, 7}  # végétation, sol nu, eau, non classé


def est_valide(classe_scl: int) -> bool:
    return classe_scl in CLASSES_VALIDES


def ndvi_masque(
    rouges: list[list[float]],
    pirs: list[list[float]],
    classes_scl: list[list[int]],
) -> list[list[float]]:
    grille = ndvi_grille(rouges, pirs)
    for i, ligne_classes in enumerate(classes_scl):
        for j, classe in enumerate(ligne_classes):
            if not est_valide(classe):
                grille[i][j] = float("nan")
    return grille


# ─────────────────────────────────────────────────────────────────────
# ÉTAPE 5 — auto-test : la logique tient debout si ces asserts passent
# ─────────────────────────────────────────────────────────────────────


def demo() -> None:
    # végétation dense : PIR haut, rouge bas → NDVI proche de +1
    assert math.isclose(ndvi_pixel(rouge=0.1, pir=0.5), 0.6666666667, rel_tol=1e-6)

    # eau : rouge > PIR → NDVI négatif
    assert ndvi_pixel(rouge=0.3, pir=0.1) < 0

    # pixel noir (nodata) : division par zéro gérée proprement
    assert math.isnan(ndvi_pixel(rouge=0.0, pir=0.0))

    # une ligne de 3 pixels
    assert ndvi_ligne([0.1, 0.3, 0.0], [0.5, 0.1, 0.0])[0] > 0

    # une grille 2×2
    grille = ndvi_grille([[0.1, 0.3], [0.0, 0.1]], [[0.5, 0.1], [0.0, 0.5]])
    assert len(grille) == 2 and len(grille[0]) == 2

    # masque : un pixel classé "nuage" (9) doit devenir NaN même s'il a des valeurs valides
    masque = ndvi_masque(
        rouges=[[0.1, 0.3]],
        pirs=[[0.5, 0.1]],
        classes_scl=[[4, 9]],  # 4=végétation (garder), 9=nuage (jeter)
    )
    assert not math.isnan(masque[0][0])
    assert math.isnan(masque[0][1])

    print("Tous les tests passent.")


if __name__ == "__main__":
    demo()
