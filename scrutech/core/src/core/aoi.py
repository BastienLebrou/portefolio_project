"""Area-of-interest resolution — the AOI-first entry point.

``resolve_aoi`` normalizes anything an algorithm might receive (INSEE code,
département, bbox, vector file, GeoDataFrame) into an :class:`Aoi`: a stable id, a
WGS84 geometry and a bbox. Every pillar keys its products on ``aoi_id``.

Commune boundaries come from geo.api.gouv.fr (all départements — fixes the old
Ardèche-only limitation), with the community france-geojson mirror as a fallback.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

# geopandas (gpd) = pandas + une colonne "geometry" spéciale : un DataFrame classique,
# mais dont les lignes portent une forme géométrique (point, ligne, polygone) et un CRS.
import geopandas as gpd
import pandas as pd

# requests = la bibliothèque standard pour faire des appels HTTP (ici vers des API web).
import requests

# shapely représente les formes géométriques elles-mêmes (indépendamment de tout CRS) :
# `box(minx, miny, maxx, maxy)` construit un rectangle ; BaseGeometry est le type de base
# commun à tous les polygones/lignes/points shapely.
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from core.constants import L93, WGS84, BBox

logger = logging.getLogger("scrutech")

GEOAPI = "https://geo.api.gouv.fr"
_MIRROR = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements"
# france-geojson fallback covers only a few départements (geo.api is the primary source).
_DEPT_SLUGS = {"07": "07-ardeche"}
_GEOJSON_FIELDS = {"fields": "code,nom,contour", "format": "geojson", "geometry": "contour"}


# @dataclass génère automatiquement __init__, __repr__ et __eq__ à partir des champs
# déclarés ci-dessous (pas besoin de les écrire à la main). `frozen=True` rend les
# instances immuables : une fois un Aoi créé, on ne peut plus modifier ses champs
# (aoi.aoi_id = "autre chose" lèverait une erreur) — utile car un Aoi sert de clé stable
# partout dans le code (tables DuckDB, chemins de fichiers...).
@dataclass(frozen=True)
class Aoi:
    """Normalized area of interest (geometry in WGS84)."""

    aoi_id: str  # identifiant stable et unique de cette emprise, ex: "insee-07005"
    label: str  # nom lisible par un humain, ex: "commune 07005"
    kind: str  # d'où vient l'AOI : insee | dept | bbox | file | gdf
    geom: BaseGeometry  # la forme géométrique elle-même (polygone), en WGS84
    bbox_wgs84: BBox  # le rectangle englobant de geom, en WGS84

    def to_gdf(self) -> gpd.GeoDataFrame:
        """The AOI as a one-row WGS84 GeoDataFrame."""
        # On enveloppe la géométrie dans un GeoDataFrame d'une seule ligne : c'est le
        # format attendu par la plupart des fonctions geopandas (reprojection, jointure...).
        return gpd.GeoDataFrame({"aoi_id": [self.aoi_id]}, geometry=[self.geom], crs=WGS84)

    def to_l93(self) -> BaseGeometry:
        """The AOI geometry reprojected to Lambert-93 (metres)."""
        # to_crs() recalcule les coordonnées dans un autre système (ici L93, en mètres) ;
        # on repart du GeoDataFrame car geopandas sait reprojeter une colonne géométrie,
        # puis .geometry.iloc[0] récupère juste la géométrie de l'unique ligne.
        return self.to_gdf().to_crs(L93).geometry.iloc[0]


def resolve_aoi(aoi: object) -> Aoi:
    """Normalize an AOI input into an :class:`Aoi` (see module docstring)."""
    # C'est LA fonction d'entrée du principe "AOI-first" : quel que soit ce que
    # l'utilisateur/l'appelant fournit comme emprise, on la transforme ici en un objet
    # Aoi unique et normalisé. La fonction teste chaque type possible dans l'ordre
    # (isinstance = "est-ce une instance de ce type ?") et s'arrête au premier qui colle.
    if isinstance(aoi, Aoi):
        return aoi  # déjà normalisé, rien à faire
    if isinstance(aoi, gpd.GeoDataFrame):
        # union_all() fusionne toutes les géométries des lignes en une seule forme
        # (utile si le GeoDataFrame contient plusieurs polygones disjoints ou adjacents).
        geom = aoi.to_crs(WGS84).union_all()
        # geom.wkb = représentation binaire (Well-Known Binary) de la géométrie ; on la
        # hash pour obtenir un identifiant court et stable, dérivé du contenu (deux AOI
        # avec exactement la même forme auront le même aoi_id).
        return _from_geom(geom, "gdf", "gdf-" + _hash(geom.wkb), "GeoDataFrame")
    if isinstance(aoi, (tuple, list)) and len(aoi) == 4 and all(_is_num(v) for v in aoi):
        # Cas "bbox" : un simple tuple (minx, miny, maxx, maxy). box(*b) construit le
        # rectangle shapely correspondant ("*b" déballe le tuple en 4 arguments séparés).
        b: BBox = tuple(float(v) for v in aoi)  # type: ignore[assignment]
        return _from_geom(box(*b), "bbox", "bbox-" + "_".join(f"{c:.4f}" for c in b), "bbox")
    if isinstance(aoi, (str, Path)):
        return _resolve_str(str(aoi))
    raise ValueError(
        f"Cannot resolve AOI from {aoi!r}: expected 'insee:XXXXX', 'dept:XX', a bbox "
        "(minx,miny,maxx,maxy), a vector file path, or a GeoDataFrame."
    )


def fetch_communes(dept: str, timeout: int = 60) -> gpd.GeoDataFrame:
    """All commune polygons of a département (WGS84), columns code/nom/geometry.

    geo.api.gouv.fr first (any département); france-geojson mirror as fallback.
    """
    try:
        params = {"codeDepartement": dept, **_GEOJSON_FIELDS}
        feats = _get_json(f"{GEOAPI}/communes", params, timeout)["features"]
        # from_features() convertit une liste de "features" GeoJSON (format standard
        # {"type": "Feature", "geometry": ..., "properties": {...}}) en GeoDataFrame.
        gdf = gpd.GeoDataFrame.from_features(feats, crs=WGS84)
    except Exception as exc:  # noqa: BLE001 — any failure -> try the static mirror
        # On attrape volontairement TOUTE exception (réseau, HTTP, JSON invalide...) car
        # l'API externe n'est pas sous notre contrôle : mieux vaut basculer sur le miroir
        # de secours que planter tout le pipeline pour une panne réseau temporaire.
        logger.warning("geo.api communes failed for %s (%s); trying mirror", dept, exc)
        gdf = _fetch_communes_mirror(dept, timeout)
    return gdf[["code", "nom", "geometry"]]


def fetch_commune(insee: str, timeout: int = 60) -> gpd.GeoDataFrame:
    """A single commune contour (WGS84) by INSEE code, columns code/nom/geometry."""
    gj = _get_json(f"{GEOAPI}/communes/{insee}", _GEOJSON_FIELDS, timeout)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    return gpd.GeoDataFrame.from_features(feats, crs=WGS84)[["code", "nom", "geometry"]]


def communes_in_aoi(aoi: object, timeout: int = 60) -> gpd.GeoDataFrame:
    """Commune polygons intersecting the AOI (WGS84) — derived from the emprise alone.

    Finds the département(s) the AOI touches (geo.api point lookups on centroid + bbox
    corners), fetches their communes, and keeps those intersecting the AOI geometry. Lets
    VegeVigie rank communes with **no Zones layer to provide**. Returns an empty frame if
    geo.api is unreachable (zonal ranking is a bonus, not a hard dependency).
    """
    a = resolve_aoi(aoi)
    frames = []
    # Une AOI peut chevaucher plusieurs départements (ex: une zone à cheval sur deux
    # frontières administratives) : on récupère donc toutes les communes de CHAQUE
    # département concerné, puis on filtrera plus bas sur celles qui touchent vraiment l'AOI.
    for dept in _depts_for_geom(a.geom, timeout):
        try:
            frames.append(fetch_communes(dept, timeout))
        except Exception as exc:  # noqa: BLE001 — skip a failing département, keep the rest
            logger.warning("communes for dept %s failed: %s", dept, exc)
    if not frames:
        return gpd.GeoDataFrame({"code": [], "nom": []}, geometry=[], crs=WGS84)
    # pd.concat empile tous les GeoDataFrame de départements les uns sous les autres
    # (ignore_index=True renumérote les lignes de 0 à N au lieu de garder les anciens index).
    allc = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=WGS84)
    # .intersects(a.geom) renvoie une série de True/False par ligne : on ne garde que les
    # communes qui touchent réellement la géométrie de l'AOI (pas juste le même département).
    return allc[allc.intersects(a.geom)].reset_index(drop=True)


def _depts_for_geom(geom: BaseGeometry, timeout: int) -> list[str]:
    """Département codes the geometry touches, via geo.api point lookups (centroid+corners)."""
    # Astuce simple et peu coûteuse : plutôt que d'interroger une API "quels départements
    # touche ce polygone ?" (qui n'existe pas forcément), on teste 5 points représentatifs
    # de la géométrie (son centre + ses 4 coins) et on demande à l'API "dans quel
    # département est ce point ?". On perd en exactitude sur les géométries très
    # tourmentées, mais ça couvre le cas courant (AOI = un seul polygone compact).
    minx, miny, maxx, maxy = geom.bounds
    c = geom.centroid
    pts = [(c.x, c.y), (minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)]
    depts: set[str] = set()  # un set évite les doublons de département automatiquement
    params = {"fields": "codeDepartement"}
    for lon, lat in pts:
        try:
            j = _get_json(f"{GEOAPI}/communes", {"lon": lon, "lat": lat, **params}, timeout)
        except Exception:  # noqa: BLE001 — a point in the sea returns nothing; ignore
            continue
        for com in j if isinstance(j, list) else []:
            if com.get("codeDepartement"):
                depts.add(com["codeDepartement"])
    return sorted(depts)


def _resolve_str(s: str) -> Aoi:
    """Interprète une chaîne comme AOI : "insee:XXXXX", "dept:XX", ou un chemin de fichier."""
    if s.startswith("insee:"):
        # split(":", 1) coupe sur le PREMIER ":" seulement (au cas où le code contiendrait
        # lui-même un ":", ce qui n'arrive pas ici mais c'est l'habitude sûre) ; [1] prend
        # la partie après le ":".
        insee = s.split(":", 1)[1]
        geom = fetch_commune(insee).to_crs(WGS84).union_all()
        return _from_geom(geom, "insee", f"insee-{insee}", f"commune {insee}")
    if s.startswith("dept:"):
        dept = s.split(":", 1)[1]
        geom = fetch_communes(dept).to_crs(WGS84).union_all()
        return _from_geom(geom, "dept", f"dept-{dept}", f"departement {dept}")
    p = Path(s)
    if p.exists():
        # Import local (à l'intérieur de la fonction, pas en haut du fichier) pour éviter
        # une dépendance circulaire : core.io pourrait un jour avoir besoin de core.aoi.
        from core.io import read_vector

        geom = read_vector(p).to_crs(WGS84).union_all()
        return _from_geom(geom, "file", f"file-{p.stem}", p.stem)
    raise ValueError(f"AOI string {s!r} is neither 'insee:'/'dept:' nor an existing file path.")


def _from_geom(geom: BaseGeometry, kind: str, aoi_id: str, label: str) -> Aoi:
    """Petite fabrique interne : calcule la bbox WGS84 et construit l'objet Aoi final."""
    b: BBox = tuple(round(float(v), 6) for v in geom.bounds)  # type: ignore[assignment]
    return Aoi(aoi_id=aoi_id, label=label, kind=kind, geom=geom, bbox_wgs84=b)


def _hash(data: bytes) -> str:
    """Empreinte courte (10 caractères hexadécimaux) et déterministe d'une suite d'octets.

    Deux appels avec exactement les mêmes octets donnent toujours le même résultat : ça
    sert à fabriquer un identifiant stable à partir d'une géométrie, sans avoir à la
    stocker en entier dans l'identifiant. MD5 n'est pas utilisé ici pour la sécurité
    (ce n'est pas un usage cryptographique), juste comme fonction de hachage rapide.
    """
    return hashlib.md5(data).hexdigest()[:10]


def _is_num(v: object) -> bool:
    """True si v est un nombre (int/float) mais pas un booléen (True/False sont des int !)."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _get_json(url: str, params: dict, timeout: int) -> dict:
    """Petit helper GET HTTP -> JSON, avec levée d'erreur si le serveur répond en échec."""
    resp = requests.get(url, params=params, timeout=timeout)
    # raise_for_status() lève une exception si le code HTTP est 4xx/5xx (erreur client ou
    # serveur) ; sans ça, une réponse d'erreur passerait inaperçue et on tenterait de
    # parser du JSON invalide juste après.
    resp.raise_for_status()
    return resp.json()


def _fetch_communes_mirror(dept: str, timeout: int) -> gpd.GeoDataFrame:
    try:
        slug = _DEPT_SLUGS[dept]
    except KeyError as exc:
        known = ", ".join(sorted(_DEPT_SLUGS))
        msg = (
            f"No france-geojson mirror slug for departement {dept!r} (known: {known}); "
            "geo.api.gouv.fr is the primary source."
        )
        raise KeyError(msg) from exc
    url = f"{_MIRROR}/{slug}/communes-{slug}.geojson"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return gpd.GeoDataFrame.from_features(resp.json()["features"], crs=WGS84)
