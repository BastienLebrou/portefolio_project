"""Traitement géo (fonctions pures GeoPandas/Shapely).

Méthode "type Cerema" : un bâtiment à usage commercial/industriel ne contenant
(ni à proximité immédiate) AUCUN établissement SIRENE actif géolocalisé est un
CANDIDAT à la vacance.

# =========================================================================== #
# AVERTISSEMENT MÉTHODOLOGIQUE (à lire avant toute exploitation) :             #
#   Le résultat = des CANDIDATS, PAS une certitude de vacance.                 #
#   - Un SIRET peut être une simple domiciliation (siège "boîte aux lettres")  #
#     sans activité réelle dans les murs -> bâtiment marqué OCCUPE à tort.      #
#   - Un local réellement vide peut conserver un SIRET résiduel non radié      #
#     -> idem.                                                                  #
#   - Inversement, un établissement actif mal géocodé (BAN imprécise) peut      #
#     tomber hors du buffer -> bâtiment marqué VACANT_CANDIDAT à tort.          #
#   La sortie sert UNIQUEMENT à PRIORISER une vérification terrain.            #
# =========================================================================== #
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from config import CRS_L93, CRS_WGS84, Config

# Colonnes finales attendues en sortie (ordre du livrable).
OUTPUT_COLS: tuple[str, ...] = (
    "id_bati", "usage_1", "usage_2", "surface_bati_m2", "hauteur",
    "nb_etab_actifs", "liste_siret", "statut_occupation",
    "code_insee", "commune", "nature", "geometry",
)


def sirene_to_points(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """DataFrame (siret, lat, lon, …) -> GeoDataFrame de points en EPSG:2154.

    Les établissements sans coordonnées valides sont exclus proprement."""
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    if df.empty:
        return gpd.GeoDataFrame(
            df.assign(geometry=[]), geometry="geometry", crs=f"EPSG:{CRS_L93}"
        )
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs=f"EPSG:{CRS_WGS84}",
    ).to_crs(CRS_L93)
    return gdf


def filter_professional(bati: gpd.GeoDataFrame, usages: frozenset[str]) -> gpd.GeoDataFrame:
    """Garde les bâtiments dont usage_1 OU usage_2 ∈ usages cibles."""
    u1 = bati["usage_1"].isin(usages) if "usage_1" in bati.columns else False
    u2 = bati["usage_2"].isin(usages) if "usage_2" in bati.columns else False
    return bati[u1 | u2].copy()


def clip_to_polygon(bati: gpd.GeoDataFrame, mask: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Garde les bâtiments dont le point représentatif tombe dans `mask`.

    On ne découpe pas les géométries (footprints conservés entiers) ; le point
    représentatif évite de compter deux fois un bâtiment à cheval sur une limite."""
    union = mask.union_all() if hasattr(mask, "union_all") else mask.unary_union
    inside = bati.representative_point().within(union)
    return bati[inside.values].copy()


def count_etablissements(
    bati_pro: gpd.GeoDataFrame,
    sirene_pts: gpd.GeoDataFrame,
    buffer_m: float,
) -> gpd.GeoDataFrame:
    """Pour chaque bâtiment : nb d'établissements actifs DANS le polygone ou dans
    un buffer de `buffer_m` (la géoloc SIRENE est à l'adresse BAN, souvent décalée
    du footprint). Ajoute nb_etab_actifs (int) et liste_siret (str concaténée)."""
    bati = bati_pro.copy().reset_index(drop=True)
    bati["id_bati"] = bati["cleabs"] if "cleabs" in bati.columns else bati.index.astype(str)

    # Polygones tampon (id + geom uniquement) pour la jointure spatiale.
    buf = gpd.GeoDataFrame(
        {"id_bati": bati["id_bati"].values},
        geometry=bati.geometry.buffer(buffer_m),
        crs=bati.crs,
    )

    if len(sirene_pts):
        joined = gpd.sjoin(
            sirene_pts[["siret", "geometry"]], buf, predicate="intersects", how="inner"
        )
        # dict.fromkeys -> dédoublonne les SIRET tout en gardant un ordre stable.
        agg = joined.groupby("id_bati")["siret"].agg(lambda s: list(dict.fromkeys(s)))
    else:
        agg = pd.Series(dtype=object)

    siret_lists = bati["id_bati"].map(agg)
    bati["nb_etab_actifs"] = siret_lists.apply(lambda x: len(x) if isinstance(x, list) else 0)
    bati["liste_siret"] = siret_lists.apply(lambda x: ",".join(x) if isinstance(x, list) else "")
    return bati


def build_result(
    bati: gpd.GeoDataFrame,
    code_insee: str,
    commune_nom: str,
) -> gpd.GeoDataFrame:
    """Assemble le livrable : surface, statut d'occupation, métadonnées, colonnes ordonnées."""
    g = bati.copy()
    g["surface_bati_m2"] = g.geometry.area.round(1)
    # statut : VACANT_CANDIDAT si aucun établissement actif rattaché, sinon OCCUPE.
    g["statut_occupation"] = np.where(
        g["nb_etab_actifs"] == 0, "VACANT_CANDIDAT", "OCCUPE"
    )
    g["code_insee"] = code_insee or ""
    g["commune"] = commune_nom or ""

    for col in OUTPUT_COLS:
        if col not in g.columns:
            g[col] = None
    return gpd.GeoDataFrame(g[list(OUTPUT_COLS)], geometry="geometry", crs=bati.crs)


def summarize(result: gpd.GeoDataFrame) -> dict[str, float]:
    """Statistiques de synthèse pour la console."""
    n_pro = len(result)
    n_vac = int((result["statut_occupation"] == "VACANT_CANDIDAT").sum())
    taux = (n_vac / n_pro * 100) if n_pro else 0.0
    return {
        "nb_batiments_pro": n_pro,
        "nb_candidats_vacants": n_vac,
        "taux_apparent_pct": round(taux, 1),
        "surface_vacante_m2": round(
            float(result.loc[result["statut_occupation"] == "VACANT_CANDIDAT", "surface_bati_m2"].sum()), 1
        ),
    }
