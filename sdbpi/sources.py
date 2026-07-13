"""Acquisition des données (avec cache local) : contour commune, bâtiments BD TOPO,
établissements SIRENE actifs géolocalisés.

Toutes les fonctions sont sans effet de bord caché : elles prennent une `Config`
+ une `Session`, lisent/écrivent uniquement dans `cfg.cache_dir`, et renvoient
des objets (Geo)DataFrame normalisés.
"""
from __future__ import annotations

import hashlib
import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

from config import (
    CRS_L93,
    CRS_WGS84,
    GEOAPI_COMMUNE_URL,
    GEOAPI_COMMUNES_URL,
    GEOFILE_COLS_DEFAUT,
    GRANDLYON_SIRENE_URL,
    NAF_CODES_FILE,
    NAF_DIV_TO_SECTION,
    NAF_SECTIONS,
    PLM_ARRONDISSEMENTS,
    REE_MAX_RESULTS,
    REE_PER_PAGE,
    REE_URL,
    WFS_PAGE_SIZE,
    WFS_TYPENAME,
    WFS_URL,
    Config,
)
from net import SourceError, get_json

BBox = tuple[float, float, float, float]


# --------------------------------------------------------------------------- #
# Utilitaires                                                                  #
# --------------------------------------------------------------------------- #
def _force_2d(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """BD TOPO renvoie des géométries 3D : on aplatit en 2D (Z inutile ici).
    Le CRS est explicitement reporté (un ndarray brut le perdrait)."""
    crs = gdf.crs
    geom_2d = shapely.force_2d(gdf.geometry.values)
    gdf = gdf.copy()
    gdf["geometry"] = gpd.GeoSeries(geom_2d, index=gdf.index, crs=crs)
    return gdf


def _bbox_key(bbox: BBox) -> str:
    return hashlib.md5(",".join(f"{c:.1f}" for c in bbox).encode()).hexdigest()[:10]


# --------------------------------------------------------------------------- #
# 1) Contour commune (geo.api.gouv.fr)                                         #
# --------------------------------------------------------------------------- #
def fetch_commune(insee: str, cfg: Config, session: requests.Session) -> tuple[gpd.GeoDataFrame, str]:
    """Contour de la commune en EPSG:2154 + son nom. Mise en cache GeoJSON."""
    cache = cfg.cache_dir / f"commune_{insee}.geojson"
    if cfg.use_cache and cache.exists():
        gj = json.loads(cache.read_text(encoding="utf-8"))
    else:
        url = GEOAPI_COMMUNE_URL.format(insee=insee)
        params = {"fields": "nom,code,contour", "format": "geojson", "geometry": "contour"}
        gj = get_json(session, url, params, cfg.http_timeout)
        if not gj or gj.get("geometry") is None:
            raise SourceError(
                f"Contour de la commune {insee} introuvable (réponse vide). "
                "Vérifier le code INSEE."
            )
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(gj, ensure_ascii=False), encoding="utf-8")

    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    gdf = gpd.GeoDataFrame.from_features(feats, crs=f"EPSG:{CRS_WGS84}").to_crs(CRS_L93)
    nom = (gj.get("properties") or feats[0].get("properties") or {}).get("nom") or insee
    return gdf, nom


def communes_in_bbox(bbox_wgs84: BBox, cfg: Config, session: requests.Session) -> list[str]:
    """Liste (approchée) des codes INSEE intersectant une bbox, par échantillonnage
    d'une grille 5x5 de points (suffisant pour une emprise de l'ordre d'une commune).
    Limite assumée : une commune entièrement intérieure et plus fine que le pas peut
    être manquée -> pour une grande bbox, préférer le mode 'geo_file'."""
    minx, miny, maxx, maxy = bbox_wgs84
    xs = np.linspace(minx, maxx, 5)
    ys = np.linspace(miny, maxy, 5)
    codes: set[str] = set()
    for x in xs:
        for y in ys:
            try:
                j = get_json(
                    session, GEOAPI_COMMUNES_URL,
                    {"lon": float(x), "lat": float(y), "fields": "code"},
                    cfg.http_timeout,
                )
            except SourceError:
                continue
            for c in j if isinstance(j, list) else []:
                if c.get("code"):
                    codes.add(c["code"])
    return sorted(codes)


# --------------------------------------------------------------------------- #
# 2) Bâtiments BD TOPO (WFS Géoplateforme)                                     #
# --------------------------------------------------------------------------- #
def fetch_batiments(bbox_l93: BBox, cfg: Config, session: requests.Session) -> gpd.GeoDataFrame:
    """Tous les bâtiments BD TOPO dans la bbox (EPSG:2154), pagination WFS gérée.

    Renvoie un GeoDataFrame (2154) avec cleabs, usage_1, usage_2, nature, hauteur,
    geometry. Cache en GeoParquet (clé = hash bbox)."""
    cache = cfg.cache_dir / f"batiments_{_bbox_key(bbox_l93)}.parquet"
    if cfg.use_cache and cache.exists():
        return gpd.read_parquet(cache)

    minx, miny, maxx, maxy = bbox_l93
    features: list[dict] = []
    start = 0
    while True:
        params = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": WFS_TYPENAME, "SRSNAME": f"EPSG:{CRS_L93}",
            # Ordre des axes en 2154 = (easting, northing) -> vérifié en live.
            "BBOX": f"{minx},{miny},{maxx},{maxy},EPSG:{CRS_L93}",
            "COUNT": str(WFS_PAGE_SIZE), "STARTINDEX": str(start),
            "OUTPUTFORMAT": "application/json",
        }
        j = get_json(session, WFS_URL, params, cfg.http_timeout)
        page = j.get("features", []) or []
        features.extend(page)
        matched = j.get("numberMatched")
        got = len(page)
        start += got
        print(f"    WFS bâtiments : {start} / {matched if matched is not None else '?'}")
        if got < WFS_PAGE_SIZE:
            break
        if isinstance(matched, int) and start >= matched:
            break
        if start > 2_000_000:  # garde-fou
            break

    if not features:
        raise SourceError(
            "WFS bâtiments : 0 feature pour l'emprise. Vérifier la bbox (EPSG:2154), "
            "la disponibilité du service ou le typename."
        )

    gdf = gpd.GeoDataFrame.from_features(features, crs=f"EPSG:{CRS_L93}")
    gdf = _force_2d(gdf)
    keep = ["cleabs", "usage_1", "usage_2", "nature", "hauteur", "geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]].copy()

    if cfg.use_cache:
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        gdf.to_parquet(cache)
    return gdf


# --------------------------------------------------------------------------- #
# 3a) SIRENE via API recherche-entreprises (partition NAF anti-plafond)        #
# --------------------------------------------------------------------------- #
def sirene_commune_codes(insee: str) -> list[str]:
    """Codes commune à interroger en SIRENE pour un code INSEE donné.
    Étend Paris/Lyon/Marseille en arrondissements (codage SIRENE réel)."""
    return PLM_ARRONDISSEMENTS.get(insee, [insee])


def _naf_codes_by_section(cfg: Config) -> dict[str, list[str]]:
    """~732 codes NAF pleins (figés) regroupés par section, pour la sous-partition."""
    codes = json.loads((cfg.base_dir / NAF_CODES_FILE).read_text(encoding="utf-8"))
    by_sec: dict[str, list[str]] = {}
    for code in codes:
        sec = NAF_DIV_TO_SECTION.get(code[:2])
        if sec:
            by_sec.setdefault(sec, []).append(code)
    return by_sec


def _query_total(session: requests.Session, cfg: Config, params: dict) -> int:
    """Nombre d'entreprises pour un filtre (sonde 1 requête)."""
    j = get_json(session, REE_URL, {**params, "page": 1, "per_page": 1}, cfg.http_timeout)
    return int(j.get("total_results") or 0)


def _collect_query(
    session: requests.Session, cfg: Config, params: dict,
    rows: list[dict], seen: set[str],
) -> int:
    """Pagine un filtre et accumule les établissements ACTIFS géolocalisés dans
    `rows` (dédoublonnés par siret via `seen`). Renvoie le nb d'ajouts."""
    added = 0
    page = 1
    while True:
        j = get_json(session, REE_URL,
                     {**params, "page": page, "per_page": REE_PER_PAGE}, cfg.http_timeout)
        results = j.get("results", []) or []
        for ent in results:
            denom = ent.get("nom_complet") or ent.get("nom_raison_sociale")
            for et in ent.get("matching_etablissements", []) or []:
                if et.get("etat_administratif") != "A":
                    continue  # matching_etablissements contient aussi des fermés
                siret = et.get("siret")
                lat, lon = et.get("latitude"), et.get("longitude")
                if not siret or siret in seen or lat in (None, "") or lon in (None, ""):
                    continue  # doublon, ou adresse non géocodée -> exclus proprement
                try:
                    lat, lon = float(lat), float(lon)
                except (TypeError, ValueError):
                    continue
                seen.add(siret)
                added += 1
                rows.append({
                    "siret": siret, "denomination": denom,
                    "activite_principale": et.get("activite_principale"),
                    "latitude": lat, "longitude": lon,
                })
        total_pages = j.get("total_pages") or 0
        if page >= total_pages or not results:
            break
        page += 1
        if cfg.request_pause_s:
            time.sleep(cfg.request_pause_s)
    return added


def fetch_sirene_api(insee: str, cfg: Config, session: requests.Session) -> pd.DataFrame:
    """Établissements ACTIFS géolocalisés d'une commune (code SIRENE) via l'API.

    Anti-plafond (10000) à deux niveaux : partition par section NAF, puis
    SOUS-PARTITION par code NAF plein pour toute section atteignant encore le cap
    (indispensable en grande ville : ex. Lyon 3e section M = 10000). Filtre
    etat_administratif=='A' au niveau établissement, exclut les lat/lon nuls.
    Colonnes : siret, denomination, activite_principale, latitude, longitude."""
    cache = cfg.cache_dir / f"sirene_api_{insee}.parquet"
    if cfg.use_cache and cache.exists():
        return pd.read_parquet(cache)

    naf_by_section = _naf_codes_by_section(cfg)
    rows: list[dict] = []
    seen: set[str] = set()

    for sec in NAF_SECTIONS:
        base = {"code_commune": insee, "etat_administratif": "A",
                "section_activite_principale": sec}
        total = _query_total(session, cfg, base)
        if total == 0:
            continue
        if total < REE_MAX_RESULTS:
            n = _collect_query(session, cfg, base, rows, seen)
            if n:
                print(f"    SIRENE {insee} section {sec}: {n}")
        else:
            # Section saturée -> on rejoue par code NAF plein (chacun < cap).
            before = len(rows)
            print(f"    SIRENE {insee} section {sec}: {total} (cap) "
                  "-> sous-partition par code NAF")
            for code in naf_by_section.get(sec, []):
                cbase = {"code_commune": insee, "etat_administratif": "A",
                         "activite_principale": code}
                ct = _query_total(session, cfg, cbase)
                if ct == 0:
                    continue
                if ct >= REE_MAX_RESULTS:
                    print(f"      [CAP PERSISTANT] {insee} {code}={ct} : incomplet "
                          "-> envisager sirene_source='geo_file'.")
                _collect_query(session, cfg, cbase, rows, seen)
            print(f"    SIRENE {insee} section {sec}: {len(rows) - before} (sous-partition)")

    df = pd.DataFrame(rows, columns=["siret", "denomination",
                                     "activite_principale", "latitude", "longitude"])
    if cfg.use_cache:
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache)
    return df


# --------------------------------------------------------------------------- #
# 3b) SIRENE via fichier départemental pré-géocodé (mode scalable)             #
# --------------------------------------------------------------------------- #
def fetch_sirene_geofile(
    cfg: Config,
    insee_filter: str | None = None,
    cols: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Lit un fichier SIRENE départemental déjà géocodé fourni par l'utilisateur
    (CSV / CSV.GZ / Parquet) et le normalise comme fetch_sirene_api.

    Le fichier officiel "Géolocalisation des établissements SIRENE" (INSEE/data.gouv)
    est national et géoloc-seule : il faut le pré-joindre au StockEtablissement pour
    disposer de etat/NAF, puis pointer cfg.sirene_geo_file dessus. Mapping de colonnes
    surchargeable via GEOFILE_COLS_DEFAUT."""
    path = cfg.sirene_geo_file
    if not path or not path.exists():
        raise SourceError(f"Fichier SIRENE géo introuvable : {path}")
    cols = {**GEOFILE_COLS_DEFAUT, **(cols or {})}

    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, dtype=str, sep=None, engine="python")

    missing = [v for k, v in cols.items() if k in ("siret", "latitude", "longitude") and v not in df.columns]
    if missing:
        raise SourceError(f"Colonnes manquantes dans {path.name} : {missing}")

    out = pd.DataFrame({
        "siret": df[cols["siret"]],
        "denomination": df.get(cols["denomination"]),
        "activite_principale": df.get(cols["activite_principale"]),
        "latitude": pd.to_numeric(df[cols["latitude"]], errors="coerce"),
        "longitude": pd.to_numeric(df[cols["longitude"]], errors="coerce"),
    })
    etat_col = cols.get("etat")
    if etat_col and etat_col in df.columns:
        out = out[df[etat_col] == "A"]
    cc_col = cols.get("code_commune")
    if insee_filter and cc_col and cc_col in df.columns:
        out = out[df[cc_col] == insee_filter]

    out = out.dropna(subset=["latitude", "longitude"]).drop_duplicates("siret")
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# 3c) SIRENE Métropole de Lyon (data.gouv) — source EN MASSE, déjà géolocalisée #
# --------------------------------------------------------------------------- #
def fetch_sirene_grandlyon(cfg: Config, session: requests.Session) -> pd.DataFrame:
    """Base Sirene de la Métropole de Lyon : ~338k établissements ACTIFS déjà
    géolocalisés (the_geom = POINT(lon lat) WGS84) sur les ~59 communes de la
    Métropole. Téléchargement (~100 Mo) mis en cache, puis normalisé en parquet.
    Idéal pour une emprise multi-communes du Grand Lyon (1 fichier vs milliers
    d'appels API). Colonnes : siret, denomination, activite_principale, latitude,
    longitude (+ insee de référence)."""
    norm = cfg.cache_dir / "sirene_grandlyon.parquet"
    if cfg.use_cache and norm.exists():
        return pd.read_parquet(norm)

    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    raw = cfg.cache_dir / "grandlyon_sirene_raw.csv"
    if not (cfg.use_cache and raw.exists()):
        try:
            with session.get(GRANDLYON_SIRENE_URL, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(raw, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        except requests.exceptions.RequestException as exc:
            raise SourceError(f"Échec téléchargement Sirene Métropole de Lyon : {exc}") from exc

    df = pd.read_csv(raw, dtype=str)
    for col in ("siret", "the_geom", "activitenaf"):
        if col not in df.columns:
            raise SourceError(f"Colonne '{col}' absente du fichier Grand Lyon (format changé ?).")

    pts = gpd.GeoSeries.from_wkt(df["the_geom"].fillna(""), crs=f"EPSG:{CRS_WGS84}")
    out = pd.DataFrame({
        "siret": df["siret"],
        "denomination": df.get("denomination"),
        "activite_principale": df["activitenaf"],
        "insee": df.get("insee"),
        "latitude": pts.y.values,
        "longitude": pts.x.values,
    })
    out = out.dropna(subset=["latitude", "longitude"]).drop_duplicates("siret").reset_index(drop=True)
    if cfg.use_cache:
        out.to_parquet(norm)
    return out
