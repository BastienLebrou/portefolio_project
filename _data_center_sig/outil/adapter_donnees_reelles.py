"""
adapter_donnees_reelles.py — Convertit des données PUBLIQUES réelles vers le
contrat d'entrée du pipeline (les fichiers data/raw/*.parquet).

Idée directrice (geo-data engineer) : le pipeline ne connaît qu'UN contrat
d'entrée. Le générateur synthétique le remplit avec des données fictives ;
cet adapter le remplit avec des données réelles. Le reste (staging, filtres,
scoring, heatmap) tourne EXACTEMENT pareil — zéro modification.

Mode d'emploi :
  1. Télécharger les sources (voir DONNEES_REELLES.md) et les déposer dans
     data/sources_reelles/ .
  2. python adapter_donnees_reelles.py            # convertit ce qui est présent
  3. python run.py --no-generate                  # exécute le pipeline dessus

L'adapter est TOLÉRANT : pour chaque couche il cherche le premier nom de colonne
connu parmi plusieurs candidats (les schémas open-data varient). Toute couche
absente est signalée et ignorée (le pipeline la traitera comme vide).

Aucune donnée n'est livrée avec le code : seul l'utilisateur fournit les fichiers.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

import config as C

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SOURCES_DIR = C.DATA_DIR / "sources_reelles"
SOURCES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers génériques
# ---------------------------------------------------------------------------
def _trouver(motifs: list[str]) -> Path | None:
    """Renvoie le premier fichier de data/sources_reelles/ matchant un motif."""
    for motif in motifs:
        for p in sorted(SOURCES_DIR.glob(motif)):
            return p
    return None


def _col(gdf, candidats: list[str]) -> str | None:
    """Premier nom de colonne présent (insensible à la casse)."""
    bas = {c.lower(): c for c in gdf.columns}
    for cand in candidats:
        if cand.lower() in bas:
            return bas[cand.lower()]
    return None


def _lire_vecteur(path: Path) -> gpd.GeoDataFrame:
    """Lit n'importe quel format vecteur GDAL (GPKG, GeoJSON, SHP, Parquet)
    et reprojette en Lambert-93 (EPSG:2154)."""
    if path.suffix.lower() == ".parquet":
        gdf = gpd.read_parquet(path)
    else:
        gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs(C.CRS_GEO)  # par défaut on suppose WGS84
    return gdf.to_crs(C.CRS_METRIQUE)


def _lire_points_csv(path: Path, lon_cands, lat_cands, sep=";") -> gpd.GeoDataFrame:
    """Lit un CSV de points (lon/lat) -> GeoDataFrame en Lambert-93."""
    df = pd.read_csv(path, sep=sep, low_memory=False)
    lon = next(
        (c for c in df.columns if c.lower() in [x.lower() for x in lon_cands]), None
    )
    lat = next(
        (c for c in df.columns if c.lower() in [x.lower() for x in lat_cands]), None
    )
    if lon is None or lat is None:
        # certains exports ARCEP/Enedis ont une colonne "geo_point" "lat,lon"
        raise ValueError(f"colonnes lon/lat introuvables dans {path.name}")
    geom = [Point(xy) for xy in zip(df[lon], df[lat])]
    return gpd.GeoDataFrame(df, geometry=geom, crs=C.CRS_GEO).to_crs(C.CRS_METRIQUE)


def _clip_aoi(gdf: gpd.GeoDataFrame, aoi: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    """Restreint une couche à l'emprise d'étude si une AOI est fournie."""
    if aoi is None or gdf.empty:
        return gdf
    return gpd.clip(gdf, aoi)


def _ecrire(gdf: gpd.GeoDataFrame, nom: str, cols: list[str]) -> None:
    """Écrit la couche normalisée dans data/raw/ (contrat du pipeline)."""
    for c in cols:
        if c not in gdf.columns:
            gdf[c] = None
    gdf = gdf[cols + ["geometry"]].set_crs(C.CRS_METRIQUE, allow_override=True)
    gdf.to_parquet(C.RAW_DIR / f"{nom}.parquet", index=False)
    print(f"  -> raw/{nom}.parquet  ({len(gdf)} entités)")


# ---------------------------------------------------------------------------
# Emprise d'étude (AOI) : contour de commune pour clipper toutes les couches
# ---------------------------------------------------------------------------
def charger_aoi() -> gpd.GeoDataFrame | None:
    """Charge un contour de commune (fichier 'commune*' ou 'aoi*')."""
    p = _trouver(
        [
            "commune*.gpkg",
            "commune*.geojson",
            "commune*.json",
            "aoi*.gpkg",
            "aoi*.geojson",
        ]
    )
    if p is None:
        print("  (pas d'AOI fournie -> aucune restriction spatiale)")
        return None
    aoi = _lire_vecteur(p)
    print(f"  AOI : {p.name} ({len(aoi)} polygone(s))")
    return aoi


# ---------------------------------------------------------------------------
# Adapters par couche  (source réelle -> contrat pipeline)
# ---------------------------------------------------------------------------
def adapt_parcelles(aoi):
    """Cadastre Etalab / PCI vecteur (cadastre.data.gouv.fr)."""
    p = _trouver(
        [
            "*parcelle*.gpkg",
            "*parcelle*.geojson",
            "*parcelle*.json",
            "cadastre*.parquet",
        ]
    )
    if not p:
        return print("  [parcelles] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_parcelle"] = g[_col(g, ["idu", "id", "numero", "IDU"])].astype(str)
    insee = _col(g, ["commune", "code_insee", "insee", "idu"])
    g["commune_insee"] = g[insee].astype(str).str[:5]
    g["commune"] = C.COMMUNE_NOM
    g["dept"] = g["commune_insee"].str[:2]
    _ecrire(g, "parcelles", ["id_parcelle", "dept", "commune", "commune_insee"])


def adapt_batiments(aoi):
    """BD TOPO IGN (bati) ou couche 'batiments' du cadastre Etalab."""
    p = _trouver(["*bati*.gpkg", "*bati*.geojson", "*bati*.shp", "*batiment*.parquet"])
    if not p:
        return print("  [batiments] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_batiment"] = g[_col(g, ["cleabs", "id", "ID", "fid"]) or g.columns[0]].astype(
        str
    )
    # BD TOPO : USAGE_1 ('Résidentiel', 'Indifférencié'...) ; NATURE pour le type
    usage = _col(g, ["usage_1", "usage", "USAGE_1"])
    g["usage"] = g[usage].astype(str) if usage else C.USAGE_RESIDENTIEL
    nature = _col(g, ["nature", "NATURE", "type"])
    g["sous_type"] = g[nature].astype(str) if nature else "Maison"
    g["dept"] = C.DEPT
    _ecrire(g, "batiments", ["id_batiment", "dept", "usage", "sous_type"])


def adapt_fibre(aoi):
    """ARCEP — IPE / 'Ma connexion internet' (data.arcep.fr). CSV ou vecteur."""
    p = _trouver(
        ["*arcep*.csv", "*fibre*.csv", "*ipe*.csv", "*fibre*.geojson", "*fibre*.gpkg"]
    )
    if not p:
        return print("  [fibre] absent")
    if p.suffix.lower() == ".csv":
        g = _lire_points_csv(
            p, ["x", "lon", "longitude", "coord_x"], ["y", "lat", "latitude", "coord_y"]
        )
    else:
        g = _lire_vecteur(p)
    g = _clip_aoi(g, aoi)
    g["id_locale"] = g[
        _col(g, ["id", "id_immeuble", "code", "imb_id"]) or g.columns[0]
    ].astype(str)
    st = _col(g, ["statut_deploiement", "statut", "etat", "eligibilite_fibre"])
    g["statut_deploiement"] = g[st].astype(str) if st else "Déployé"
    g["operateur"] = g[_col(g, ["operateur", "op"]) or "id_locale"]
    g["dept"] = C.DEPT
    _ecrire(g, "fibre", ["id_locale", "dept", "statut_deploiement", "operateur"])


def adapt_energie(aoi):
    """Enedis Open Data — postes sources / capacités d'accueil (opendata.enedis.fr)."""
    p = _trouver(
        [
            "*enedis*.csv",
            "*poste*source*.csv",
            "*capacite*.csv",
            "*poste*.geojson",
            "*enedis*.geojson",
        ]
    )
    if not p:
        return print("  [energie] absent")
    if p.suffix.lower() == ".csv":
        g = _lire_points_csv(p, ["x", "lon", "longitude"], ["y", "lat", "latitude"])
    else:
        g = _lire_vecteur(p)
    g = _clip_aoi(g, aoi)
    g["id_poste_source"] = g[
        _col(g, ["code", "id", "nom", "poste"]) or g.columns[0]
    ].astype(str)
    pmax = _col(g, ["capacite_max_kva", "puissance_max_kva", "s_max_kva"])
    pdispo = _col(
        g, ["capacite_dispo_kva", "puissance_disponible_kva", "capacite_reservee_kva"]
    )
    g["puissance_max_kva"] = pd.to_numeric(g[pmax], errors="coerce") if pmax else 0.0
    g["puissance_disponible_kva"] = (
        pd.to_numeric(g[pdispo], errors="coerce") if pdispo else 0.0
    )
    g["dept"] = C.DEPT
    _ecrire(
        g,
        "energie",
        ["id_poste_source", "dept", "puissance_max_kva", "puissance_disponible_kva"],
    )


def adapt_irve(aoi):
    """Bornes de recharge VE — IRVE (data.gouv.fr / transport.data.gouv)."""
    p = _trouver(["*irve*.csv", "*borne*.csv", "*irve*.geojson"])
    if not p:
        return print("  [bornes_ve] absent")
    if p.suffix.lower() == ".csv":
        g = _lire_points_csv(
            p,
            ["x", "lon", "longitude", "consolidated_longitude"],
            ["y", "lat", "latitude", "consolidated_latitude"],
        )
    else:
        g = _lire_vecteur(p)
    g = _clip_aoi(g, aoi)
    g["id_borne"] = g[
        _col(g, ["id_pdc_local", "id", "id_station"]) or g.columns[0]
    ].astype(str)
    _ecrire(g, "bornes_ve", ["id_borne"])


def adapt_pv(aoi):
    """Installations photovoltaïques — registre ODRÉ / Enedis-RTE."""
    p = _trouver(
        ["*photovolt*.csv", "*pv*.csv", "*installation*.geojson", "*pv*.geojson"]
    )
    if not p:
        return print("  [pv] absent")
    if p.suffix.lower() == ".csv":
        g = _lire_points_csv(p, ["x", "lon", "longitude"], ["y", "lat", "latitude"])
    else:
        g = _lire_vecteur(p)
    g = _clip_aoi(g, aoi)
    g["id_pv"] = g[_col(g, ["id", "code"]) or g.columns[0]].astype(str)
    _ecrire(g, "pv", ["id_pv"])


def adapt_abf(aoi):
    """Monuments Historiques — Atlas des patrimoines / Mérimée / GPU."""
    p = _trouver(
        ["*monument*.geojson", "*mh*.geojson", "*abf*.gpkg", "*patrimoine*.geojson"]
    )
    if not p:
        return print("  [abf] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_monument"] = g[_col(g, ["id", "ref", "reference"]) or g.columns[0]].astype(
        str
    )
    nom = _col(g, ["nom", "appellation", "titre", "name"])
    g["nom"] = g[nom].astype(str) if nom else "Monument historique"
    _ecrire(g, "abf", ["id_monument", "nom"])


def adapt_ppri(aoi):
    """Zones inondables — Géorisques (zonage réglementaire PPRI)."""
    p = _trouver(
        ["*ppri*.geojson", "*inondation*.geojson", "*risque*.gpkg", "*ppr*.geojson"]
    )
    if not p:
        return print("  [ppri] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_ppri"] = g[_col(g, ["id", "code", "gid"]) or g.columns[0]].astype(str)
    niv = _col(g, ["niveau_risque", "niveau", "alea", "classe"])
    g["niveau_risque"] = g[niv].astype(str) if niv else "Inconnu"
    _ecrire(g, "ppri", ["id_ppri", "niveau_risque"])


def adapt_ebc(aoi):
    """Espaces Boisés Classés — Géoportail de l'Urbanisme (prescriptions surfaciques)."""
    p = _trouver(
        ["*ebc*.geojson", "*boise*.geojson", "*prescription*.gpkg", "*ebc*.gpkg"]
    )
    if not p:
        return print("  [ebc] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_ebc"] = g[_col(g, ["id", "code", "gid"]) or g.columns[0]].astype(str)
    _ecrire(g, "ebc", ["id_ebc"])


def adapt_voirie(aoi):
    """Voirie — BD TOPO (troncon_de_route) ou OpenStreetMap."""
    p = _trouver(
        ["*route*.geojson", "*voie*.geojson", "*troncon*.gpkg", "*voirie*.geojson"]
    )
    if not p:
        return print("  [voirie] absent")
    g = _clip_aoi(_lire_vecteur(p), aoi)
    g["id_troncon"] = g[_col(g, ["cleabs", "id", "gid"]) or g.columns[0]].astype(str)
    _ecrire(g, "voirie", ["id_troncon"])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def convertir_tout() -> None:
    print(f"Adapter données réelles -> data/raw/  (sources : {SOURCES_DIR})")
    aoi = charger_aoi()
    for fn in (
        adapt_parcelles,
        adapt_batiments,
        adapt_fibre,
        adapt_energie,
        adapt_irve,
        adapt_pv,
        adapt_abf,
        adapt_ppri,
        adapt_ebc,
        adapt_voirie,
    ):
        try:
            fn(aoi)
        except Exception as e:  # une source mal formée ne bloque pas les autres
            print(f"  [!] {fn.__name__} : {e}")
    print("\nConversion terminée. Lance ensuite :  python run.py --no-generate")


if __name__ == "__main__":
    convertir_tout()
