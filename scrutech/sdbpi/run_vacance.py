"""POC — détection de bâtiments professionnels potentiellement vacants.

Croisement open data BD TOPO (bâti) x SIRENE (activité) sur une emprise.
Méthode type Cerema : bâtiment commercial/industriel SANS établissement SIRENE
actif géolocalisé dedans (ou à proximité immédiate) = CANDIDAT vacant.

# IMPORTANT : la sortie liste des CANDIDATS, pas des certitudes (domiciliation
# sans usage réel, SIRET résiduel, géocodage BAN imprécis…). Elle sert à
# PRIORISER une vérification terrain. Voir l'avertissement dans processing.py.

Exemples :
    python run_vacance.py --insee 01053
    python run_vacance.py --insee 01053 --buffer 25
    python run_vacance.py --bbox 5.21,46.19,5.25,46.22
    python run_vacance.py --emprise emprise_etude.parquet --source grandlyon   # Grand Lyon
    python run_vacance.py --insee 69123 --source geo_file --geo-file C:/data/sirene_geo_69.parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import CRS_L93, CRS_WGS84, Config
from net import SourceError, make_session
from processing import (
    build_result,
    clip_to_polygon,
    count_etablissements,
    filter_professional,
    sirene_to_points,
    summarize,
)
from sources import (
    communes_in_bbox,
    fetch_batiments,
    fetch_commune,
    fetch_sirene_api,
    fetch_sirene_geofile,
    fetch_sirene_grandlyon,
    sirene_commune_codes,
)

BBox = tuple[float, float, float, float]


# --------------------------------------------------------------------------- #
# Résolution de l'emprise                                                      #
# --------------------------------------------------------------------------- #
def _bbox_wgs84_to_l93(bbox: BBox) -> BBox:
    """Reprojette une bbox WGS84 (minx,miny,maxx,maxy) en Lambert-93."""
    minx, miny, maxx, maxy = bbox
    # Reprojeter les 4 coins (la distorsion Lambert peut déborder un coin).
    pts = gpd.GeoSeries(
        gpd.points_from_xy([minx, maxx, minx, maxx], [miny, maxy, maxy, miny]),
        crs=f"EPSG:{CRS_WGS84}",
    ).to_crs(CRS_L93)
    xs, ys = pts.x.tolist(), pts.y.tolist()
    return (min(xs), min(ys), max(xs), max(ys))


def _read_emprise(path: Path) -> gpd.GeoDataFrame:
    """Charge un polygone d'emprise (.parquet/.gpkg/.geojson) en EPSG:2154."""
    g = gpd.read_parquet(path) if path.suffix.lower() == ".parquet" else gpd.read_file(path)
    if g.crs is None:
        g = g.set_crs(CRS_L93)  # hypothèse Lambert-93 (couches d'étude FR)
    return g.to_crs(CRS_L93)[["geometry"]]


def resolve_emprise(cfg: Config, session) -> tuple[gpd.GeoDataFrame | None, BBox, str, str, list[str]]:
    """Renvoie (mask_l93|None, bbox_l93, code_insee, nom, communes_insee)."""
    # Mode emprise polygonale depuis fichier (prioritaire).
    if cfg.zone_emprise_file:
        emp = _read_emprise(cfg.zone_emprise_file)
        bbox_l93 = tuple(float(v) for v in emp.total_bounds)
        communes: list[str] = []
        if cfg.sirene_source == "api":  # l'API a besoin des communes ; grandlyon non
            bb = tuple(float(v) for v in emp.to_crs(CRS_WGS84).total_bounds)
            base = communes_in_bbox(bb, cfg, session)
            communes = sorted({c2 for c in base for c2 in sirene_commune_codes(c)})
        return emp, bbox_l93, "", cfg.label, communes

    if cfg.zone_insee:
        commune, nom = fetch_commune(cfg.zone_insee, cfg, session)
        bbox_l93 = tuple(float(v) for v in commune.total_bounds)
        # Paris/Lyon/Marseille : SIRENE interrogé par arrondissement, mais le
        # contour et les bâtiments restent ceux de la commune entière.
        communes = sirene_commune_codes(cfg.zone_insee)
        return commune, bbox_l93, cfg.zone_insee, nom, communes

    # Mode bbox
    bbox_wgs = cfg.zone_bbox
    bbox_l93 = _bbox_wgs84_to_l93(bbox_wgs)
    mask = gpd.GeoDataFrame(
        geometry=[gpd.GeoSeries.from_wkt(
            [f"POLYGON(({bbox_l93[0]} {bbox_l93[1]},{bbox_l93[2]} {bbox_l93[1]},"
             f"{bbox_l93[2]} {bbox_l93[3]},{bbox_l93[0]} {bbox_l93[3]},"
             f"{bbox_l93[0]} {bbox_l93[1]}))"]).iloc[0]],
        crs=f"EPSG:{CRS_L93}",
    )
    communes = communes_in_bbox(bbox_wgs, cfg, session) if cfg.sirene_source == "api" else []
    return mask, bbox_l93, "", cfg.label, communes


# --------------------------------------------------------------------------- #
# Chargement SIRENE selon la source                                           #
# --------------------------------------------------------------------------- #
def load_sirene(cfg: Config, session, communes: list[str]) -> pd.DataFrame:
    if cfg.sirene_source == "grandlyon":
        print("  [SIRENE] Base Sirene Métropole de Lyon (actifs géolocalisés, ~338k)…")
        return fetch_sirene_grandlyon(cfg, session)

    if cfg.sirene_source == "geo_file":
        print("  [SIRENE] lecture du fichier départemental pré-géocodé…")
        return fetch_sirene_geofile(cfg, insee_filter=cfg.zone_insee)

    if not communes:
        raise SourceError(
            "Mode API : aucune commune résolue pour l'emprise. "
            "Fournir --insee, ou utiliser --source geo_file pour une bbox large."
        )
    frames = []
    for insee in communes:
        print(f"  [SIRENE] API recherche-entreprises commune {insee} "
              "(partition par section NAF)…")
        frames.append(fetch_sirene_api(insee, cfg, session))
    return pd.concat(frames, ignore_index=True).drop_duplicates("siret") if frames else pd.DataFrame()


# --------------------------------------------------------------------------- #
# Pipeline                                                                     #
# --------------------------------------------------------------------------- #
def run(cfg: Config) -> gpd.GeoDataFrame:
    cfg.validate()
    session = make_session(cfg.user_agent, cfg.http_retries)

    print(f"[1/5] Emprise : {cfg.label}")
    mask, bbox_l93, code_insee, nom, communes = resolve_emprise(cfg, session)
    print(f"      -> {nom}  | bbox 2154 = "
          f"{tuple(round(v) for v in bbox_l93)}")

    print("[2/5] Bâtiments BD TOPO (WFS)…")
    bati = fetch_batiments(bbox_l93, cfg, session)
    if mask is not None:
        bati = clip_to_polygon(bati, mask)
    print(f"      -> {len(bati)} bâtiments dans l'emprise")

    print(f"[3/5] Filtre usages cibles {sorted(cfg.usages_cible)}…")
    bati_pro = filter_professional(bati, cfg.usages_cible)
    print(f"      -> {len(bati_pro)} bâtiments professionnels")
    if bati_pro.empty:
        print("      (aucun bâtiment professionnel : rien à croiser)")

    print(f"[4/5] SIRENE actifs géolocalisés (source={cfg.sirene_source})…")
    sirene_df = load_sirene(cfg, session, communes)
    sirene_pts = sirene_to_points(sirene_df)
    n_total = len(sirene_pts)
    # Emprise custom (bbox/fichier) : on restreint les points à l'emprise élargie
    # du buffer (sans perdre les appariements de bordure). Mode commune : on garde
    # tous les points (un géocodage BAN peut tomber juste hors de la limite).
    if code_insee == "" and mask is not None and n_total:
        buf = mask.buffer(cfg.buffer_m)
        zone = buf.union_all() if hasattr(buf, "union_all") else buf.unary_union
        sirene_pts = sirene_pts[sirene_pts.within(zone).values].copy()
        print(f"      -> {n_total} établissements chargés ; "
              f"{len(sirene_pts)} dans l'emprise (+{cfg.buffer_m:.0f} m)")
    else:
        print(f"      -> {len(sirene_pts)} établissements actifs géolocalisés")

    print(f"[5/5] Jointure spatiale (buffer {cfg.buffer_m} m) + statut…")
    counted = count_etablissements(bati_pro, sirene_pts, cfg.buffer_m)
    result = build_result(counted, code_insee, nom)
    return result


def write_outputs(result: gpd.GeoDataFrame, cfg: Config) -> tuple[str, str]:
    out_dir = cfg.output_dir / cfg.label
    out_dir.mkdir(parents=True, exist_ok=True)
    gpkg = out_dir / f"batiments_vacance_{cfg.label}.gpkg"
    parquet = out_dir / f"batiments_vacance_{cfg.label}.parquet"
    # GeoPackage + GeoParquet en parallèle.
    result.to_file(gpkg, driver="GPKG", layer="vacance")
    result.to_parquet(parquet)
    return str(gpkg), str(parquet)


def print_summary(result: gpd.GeoDataFrame, cfg: Config, gpkg: str, parquet: str) -> None:
    s = summarize(result)
    print("\n" + "=" * 64)
    print(f"  RÉSUMÉ — {cfg.label}")
    print("=" * 64)
    print(f"  Bâtiments professionnels       : {s['nb_batiments_pro']}")
    print(f"  Candidats vacants              : {s['nb_candidats_vacants']}")
    print(f"  Taux apparent de vacance       : {s['taux_apparent_pct']} %")
    print(f"  Surface candidate vacante      : {s['surface_vacante_m2']:.0f} m²")
    print("-" * 64)
    print(f"  GeoPackage  : {gpkg}")
    print(f"  GeoParquet  : {parquet}")
    print("=" * 64)
    print("  RAPPEL : ce sont des CANDIDATS (domiciliation, SIRET résiduel,")
    print("  géocodage imprécis). À confirmer par vérification terrain.")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def build_config_from_args(argv: list[str] | None = None) -> Config:
    p = argparse.ArgumentParser(description="POC détection bâtiments pro vacants.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--insee", help="Code INSEE de la commune (ex. 01053).")
    g.add_argument("--bbox", help="Emprise WGS84 'minx,miny,maxx,maxy'.")
    g.add_argument("--emprise", help="Fichier polygone d'emprise (.parquet/.gpkg/.geojson).")
    p.add_argument("--buffer", type=float, default=15.0, help="Buffer mètres (défaut 15).")
    p.add_argument("--source", choices=("api", "geo_file", "grandlyon"), default="api",
                   help="Source SIRENE (api | geo_file | grandlyon ; défaut api).")
    p.add_argument("--geo-file", help="Chemin fichier SIRENE géo (mode geo_file).")
    p.add_argument("--usages", help="Usages cibles séparés par ';' "
                   "(défaut 'Commercial et services;Industriel').")
    p.add_argument("--no-cache", action="store_true", help="Ignore le cache local.")
    a = p.parse_args(argv)

    cfg = Config(buffer_m=a.buffer, sirene_source=a.source, use_cache=not a.no_cache)
    if a.emprise:
        cfg = cfg.with_(zone_insee=None, zone_bbox=None, zone_emprise_file=Path(a.emprise))
    elif a.bbox:
        coords = tuple(float(x) for x in a.bbox.split(","))
        if len(coords) != 4:
            p.error("--bbox attend 4 nombres 'minx,miny,maxx,maxy'.")
        cfg = cfg.with_(zone_insee=None, zone_bbox=coords)
    else:
        cfg = cfg.with_(zone_insee=a.insee or "01053", zone_bbox=None)
    if a.geo_file:
        cfg = cfg.with_(sirene_geo_file=Path(a.geo_file))
    if a.usages:
        cfg = cfg.with_(usages_cible=frozenset(u.strip() for u in a.usages.split(";") if u.strip()))
    return cfg


def main(argv: list[str] | None = None) -> int:
    # Console Windows en UTF-8 pour les accents.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cfg = build_config_from_args(argv)
    try:
        result = run(cfg)
    except SourceError as exc:
        print(f"\n[ERREUR SOURCE] {exc}", file=sys.stderr)
        return 2
    gpkg, parquet = write_outputs(result, cfg)
    print_summary(result, cfg, gpkg, parquet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
