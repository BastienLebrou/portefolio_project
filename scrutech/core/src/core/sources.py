"""AOI-driven data acquisition — the layers every pillar derives from a study area.

CE QUE ÇA FAIT : à partir d'une **seule emprise** (AOI), va chercher en open data les
couches vectorielles dont PAF et Écobuage ont besoin — **bâti**, **forêt**, **routes** —
sans que l'utilisateur ait à fournir la moindre couche. C'est ce qui rend les outils
« emprise seule en entrée ».

Source : BD TOPO® via le WFS Géoplateforme IGN (``data.geopf.fr``), pagination gérée
(COUNT plafonné à 5000/requête → ``STARTINDEX``), géométries 3D aplaties en 2D, résultat
clippé exactement à l'emprise et renvoyé en Lambert-93 (mètres).
"""

from __future__ import annotations

import logging

import geopandas as gpd
import pandas as pd
import requests
import shapely

from core.aoi import Aoi, resolve_aoi
from core.constants import L93

logger = logging.getLogger("scrutech")

WFS_URL = "https://data.geopf.fr/wfs/ows"
WFS_PAGE_SIZE = 5000

BUILDINGS_TYPENAME = "BDTOPO_V3:batiment"
VEGETATION_TYPENAME = "BDTOPO_V3:zone_de_vegetation"
ROADS_TYPENAME = "BDTOPO_V3:troncon_de_route"

# Biodiversity reservoirs / protected areas — INPN (patrinat) layers on the Géoplateforme
# WFS, same server as BD TOPO. Verified live 2026-08 (typenames return geometry in L93).
RESERVOIR_TYPENAMES = {
    "natura2000_sic": "patrinat_sic:sic",  # Natura 2000 — Directive Habitats
    "natura2000_zps": "patrinat_zps:zps",  # Natura 2000 — Directive Oiseaux
    "znieff1": "patrinat_znieff1:znieff1",  # ZNIEFF type 1 (secteurs de fort intérêt)
    "znieff2": "patrinat_znieff2:znieff2",  # ZNIEFF type 2 (grands ensembles)
    "ramsar": "patrinat_ramsar:ramsar",  # zones humides d'importance internationale
}
# TVB corridors are regional (SRCE/SRADDET), not on this national WFS — added later.
DEFAULT_RESERVOIR_KINDS = ("natura2000_sic", "natura2000_zps", "znieff1", "znieff2")

# BD TOPO zone_de_vegetation "nature" values that count as forest for the WUI/fuel maths.
# Matched case-insensitively as substrings (covers "Forêt fermée de feuillus", "Bois", …).
FOREST_NATURE_HINTS = ("forêt", "foret", "bois", "haie")


# Le "*" dans une signature de fonction Python force tous les arguments qui suivent à
# être passés par leur nom (`fetch_buildings(aoi, timeout=60)`), jamais par position
# (`fetch_buildings(aoi, 60)` serait refusé) — ça évite les erreurs d'appel silencieuses
# quand une fonction a beaucoup de paramètres optionnels.
def fetch_buildings(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """All BD TOPO buildings within the AOI (EPSG:2154). Columns: usage_1/2, nature, hauteur."""
    keep = ["cleabs", "usage_1", "usage_2", "nature", "hauteur"]
    return fetch_bdtopo(aoi, BUILDINGS_TYPENAME, keep, timeout=timeout)


def fetch_forest(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """BD TOPO wooded zones within the AOI (EPSG:2154), filtered to forest natures."""
    veg = fetch_bdtopo(aoi, VEGETATION_TYPENAME, ["cleabs", "nature"], timeout=timeout)
    if veg.empty or "nature" not in veg.columns:
        return veg
    # fillna("") remplace les valeurs manquantes par une chaîne vide (évite une erreur sur
    # le .lower() suivant), puis .str.lower() met tout en minuscules pour comparer sans
    # se soucier de la casse ("Forêt" vs "forêt").
    nat = veg["nature"].fillna("").str.lower()
    # Pour chaque ligne, `mask` vaut True si l'un des mots-clés de FOREST_NATURE_HINTS
    # apparaît dans le texte de la colonne "nature" (ex: "forêt fermée de feuillus"
    # contient "forêt" -> True). .apply() exécute cette petite fonction sur chaque ligne.
    mask = nat.apply(lambda s: any(h in s for h in FOREST_NATURE_HINTS))
    return veg[mask].copy()  # .copy() évite un avertissement pandas sur les vues partielles


def fetch_roads(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """BD TOPO road segments within the AOI (EPSG:2154) — for accessibility/distance."""
    return fetch_bdtopo(aoi, ROADS_TYPENAME, ["cleabs", "nature", "importance"], timeout=timeout)


def fetch_biodiversity_reservoirs(
    aoi: object,
    kinds: tuple[str, ...] | None = None,
    *,
    timeout: int = 120,
) -> gpd.GeoDataFrame:
    """Protected areas / biodiversity reservoirs intersecting the AOI (EPSG:2154).

    Combines the requested INPN layers (default: Natura 2000 SIC + ZPS, ZNIEFF 1 + 2) into
    one GeoDataFrame with a ``kind`` label and the site name — the "enjeu" input of biotrame.
    """
    kinds = kinds or DEFAULT_RESERVOIR_KINDS
    frames = []
    for kind in kinds:
        gdf = fetch_bdtopo(aoi, RESERVOIR_TYPENAMES[kind], ["nom_site"], timeout=timeout)
        if gdf.empty:
            continue
        # On étiquette chaque couche avec son "kind" (natura2000_sic, znieff1, ...) avant
        # de tout regrouper : ça permet, une fois fusionné, de savoir d'où vient chaque ligne.
        gdf["kind"] = kind
        if "nom_site" not in gdf.columns:
            gdf["nom_site"] = None
        frames.append(gdf[["kind", "nom_site", "geometry"]])
    if not frames:
        return gpd.GeoDataFrame({"kind": [], "nom_site": []}, geometry=[], crs=L93)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=L93)


def fetch_tvb_corridors(
    aoi: object,
    typename: str,
    *,
    wfs_url: str,
    keep: list[str] | None = None,
    timeout: int = 120,
) -> gpd.GeoDataFrame:
    """Trame Verte et Bleue corridors for the AOI, from a **regional** WFS (SRCE/SRADDET).

    There is no national TVB WFS — each DREAL publishes its SRCE on its own server, with its
    own ``typename``. Pass the region's ``wfs_url`` + ``typename`` (e.g. from the biotrame
    algorithm parameters). Returns the corridor geometries (EPSG:2154), clipped to the AOI.
    """
    return fetch_bdtopo(aoi, typename, keep or [], timeout=timeout, wfs_url=wfs_url)


def fetch_bdtopo(
    aoi: object,
    typename: str,
    keep: list[str],
    *,
    timeout: int = 120,
    clip: bool = True,
    wfs_url: str = WFS_URL,
) -> gpd.GeoDataFrame:
    """Fetch one WFS layer within the AOI's bbox (paginated), clipped to the AOI.

    Defaults to the Géoplateforme WFS (BD TOPO / INPN); ``wfs_url`` targets any other WFS 2.0
    endpoint (e.g. a regional DREAL server for the TVB). Returns a GeoDataFrame in EPSG:2154
    with the ``keep`` columns that exist (plus geometry).
    """
    a: Aoi = resolve_aoi(aoi)  # normalise n'importe quelle forme d'AOI reçue en entrée
    aoi_l93 = a.to_l93()
    # bounds = (minx, miny, maxx, maxy) : on interroge le serveur WFS avec un simple
    # rectangle englobant (plus simple/rapide côté serveur qu'un polygone précis), puis
    # on affine le résultat avec `clip` un peu plus bas.
    minx, miny, maxx, maxy = aoi_l93.bounds

    features = _paginated_wfs(typename, (minx, miny, maxx, maxy), timeout, wfs_url)
    if not features:
        logger.warning("WFS %s: 0 feature for AOI %s", typename, a.aoi_id)
        return gpd.GeoDataFrame({c: [] for c in keep}, geometry=[], crs=L93)

    gdf = gpd.GeoDataFrame.from_features(features, crs=L93)
    gdf = _force_2d(gdf)
    # On ne garde que les colonnes demandées qui existent VRAIMENT dans la réponse (une
    # couche WFS peut ne pas avoir tous les attributs attendus selon le territoire).
    cols = [c for c in keep if c in gdf.columns]
    gdf = gdf[[*cols, "geometry"]].copy()
    if clip:
        # Le rectangle englobant (bbox) ramène des objets qui touchent le rectangle mais
        # pas forcément l'AOI elle-même (un polygone n'est pas un rectangle) : `clip`
        # filtre précisément sur l'intersection avec la vraie géométrie de l'AOI.
        gdf = gdf[gdf.intersects(aoi_l93)].copy()
    return gdf


def _paginated_wfs(
    typename: str, bbox_l93: tuple, timeout: int, wfs_url: str = WFS_URL
) -> list[dict]:
    """Page through a WFS GetFeature (EPSG:2154 bbox) and return raw GeoJSON features."""
    # WFS (Web Feature Service) est un protocole standard pour interroger des couches
    # géographiques via HTTP. Le serveur ne renvoie jamais tout d'un coup : il limite
    # chaque réponse à WFS_PAGE_SIZE objets ("features"). On doit donc faire plusieurs
    # requêtes successives ("pages"), chacune démarrant où la précédente s'est arrêtée
    # (STARTINDEX), jusqu'à ce qu'une page revienne incomplète (= c'était la dernière).
    minx, miny, maxx, maxy = bbox_l93
    features: list[dict] = []
    start = 0
    while True:  # boucle "tant que vrai" : on sort explicitement avec `break` plus bas
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": typename,
            "SRSNAME": f"EPSG:{L93.split(':')[1]}",
            # In EPSG:2154 the axis order is (easting, northing) — verified live.
            "BBOX": f"{minx},{miny},{maxx},{maxy},{L93}",
            "COUNT": str(WFS_PAGE_SIZE),
            "STARTINDEX": str(start),
            "OUTPUTFORMAT": "application/json",
        }
        resp = requests.get(wfs_url, params=params, timeout=timeout)
        resp.raise_for_status()
        # `or []` protège contre le cas où .get("features") renverrait None au lieu
        # d'une liste vide (réponse JSON inattendue) — évite un crash sur `len(page)`.
        page = resp.json().get("features", []) or []
        features.extend(page)  # ajoute les éléments de `page` à la liste `features`
        got = len(page)
        start += got
        logger.info("WFS %s: %d features", typename, start)
        if got < WFS_PAGE_SIZE:
            # Une page plus petite que la taille demandée = il n'y a plus rien après :
            # c'était la dernière page, on arrête la boucle.
            break
        if start > 2_000_000:  # ponytail: guard-rail, tile the AOI if you ever hit this
            # Garde-fou de sécurité : si on dépasse 2 millions d'objets, on arrête pour
            # éviter une boucle infinie/coûteuse plutôt que de continuer indéfiniment.
            logger.warning("WFS %s: hit 2M guard-rail, result truncated", typename)
            break
    return features


def _force_2d(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """BD TOPO returns 3D geometries; flatten to 2D (Z is useless here), keeping the CRS."""
    # BD TOPO fournit parfois une altitude (Z) en plus de X/Y ; comme aucun calcul ici
    # n'en a besoin, on l'enlève pour simplifier (certains outils gèrent mal les
    # géométries 3D). `shapely.force_2d` fait cette conversion géométrie par géométrie.
    crs = gdf.crs
    out = gdf.copy()
    out["geometry"] = gpd.GeoSeries(shapely.force_2d(gdf.geometry.values), index=gdf.index, crs=crs)
    return out
