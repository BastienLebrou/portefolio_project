"""
telecharge_ebc.py — Télécharge les Espaces Boisés Classés (EBC) d'une commune
depuis le Géoportail de l'Urbanisme (Géoplateforme IGN), via WFS.

Source  : WFS https://data.geopf.fr/wfs/ows
Couche  : wfs_du:prescription_surf  (prescriptions surfaciques des PLU)
Filtre  : typepsc = '01'  (code CNIG = Espace Boisé Classé)

Sortie  : Data_alba/ebc.parquet  (GeoParquet, EPSG:2154), prête pour l'analyse.

Usage :
    python telecharge_ebc.py                 # commune d'Alba (bbox auto)
    python telecharge_ebc.py --insee 07005
"""

import sys
import json
import argparse
import tempfile
import urllib.parse
import urllib.request

import geopandas as gpd

import config as C

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WFS = "https://data.geopf.fr/wfs/ows"
COUCHE = "wfs_du:prescription_surf"
TYPEPSC_EBC = "01"  # code CNIG des EBC
DATA_ALBA = C.BASE_DIR.parent / "Data_alba"
UA = {"User-Agent": "data-center-sig/1.0 (projet perso)"}


def _bbox_commune() -> tuple[float, float, float, float]:
    """BBOX (EPSG:2154) de la commune : lue depuis commune.parquet si présent,
    sinon emprise par défaut d'Alba-la-Romaine."""
    p = DATA_ALBA / "commune.parquet"
    if p.exists():
        g = gpd.read_parquet(p).to_crs(C.CRS_METRIQUE)
        xmin, ymin, xmax, ymax = g.total_bounds
        return (xmin - 50, ymin - 50, xmax + 50, ymax + 50)
    return (823283.0, 6381644.0, 830194.0, 6389887.0)


def _requete_wfs(bbox, count=5000) -> dict:
    """GetFeature WFS en GeoJSON, restreint à la BBOX (EPSG:2154).

    Note : on n'utilise PAS STARTINDEX (pagination) car la couche n'a pas de
    clé primaire -> GeoServer exige alors un SORTBY. Pour une commune, le
    nombre de prescriptions tient largement sous la limite COUNT.
    """
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": COUCHE,
        "SRSNAME": f"EPSG:{C.CRS_METRIQUE}",
        "BBOX": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:{C.CRS_METRIQUE}",
        "OUTPUTFORMAT": "application/json",
        "COUNT": str(count),
    }
    url = WFS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def telecharger(insee: str, out_dir) -> None:
    bbox = _bbox_commune()
    print(f"EBC — commune {insee} | BBOX 2154 = {tuple(round(b) for b in bbox)}")

    fc = _requete_wfs(bbox)
    features = fc.get("features", [])
    print(f"  {len(features)} prescriptions surfaciques dans l'emprise")
    if len(features) >= 5000:
        print("  [!] limite 5000 atteinte — affiner la BBOX si besoin")

    if not features:
        print(
            "  Aucune prescription surfacique sur cette emprise "
            "(commune sans PLU sur le GPU, ou hors couverture)."
        )
        return

    gdf = gpd.GeoDataFrame.from_features(features, crs=C.CRS_METRIQUE)

    # Filtre EBC : typepsc == '01'
    col = next((c for c in gdf.columns if c.lower() == "typepsc"), None)
    if col is None:
        print(f"  [!] colonne 'typepsc' absente ; colonnes = {list(gdf.columns)}")
        return
    ebc = gdf[gdf[col].astype(str) == TYPEPSC_EBC].copy()
    print(f"  -> {len(ebc)} EBC (typepsc='01') sur {len(gdf)} prescriptions")

    if ebc.empty:
        print("  (aucun Espace Boisé Classé sur cette commune)")
        return

    # Découpe sur le contour communal si disponible
    com = DATA_ALBA / "commune.parquet"
    if com.exists():
        aoi = gpd.read_parquet(com).to_crs(C.CRS_METRIQUE)
        ebc = gpd.clip(ebc, aoi)

    out_dir.mkdir(parents=True, exist_ok=True)
    # On garde un identifiant et la géométrie (contrat minimal de l'analyse)
    idc = next((c for c in ebc.columns if c.lower() in ("idpsc", "id", "gid")), None)
    ebc["id_ebc"] = (
        ebc[idc].astype(str) if idc else [f"EBC{i:04d}" for i in range(len(ebc))]
    )
    ebc = ebc[["id_ebc", "geometry"]].set_crs(C.CRS_METRIQUE, allow_override=True)
    dest = out_dir / "ebc.parquet"
    ebc.to_parquet(dest, index=False)
    print(f"  écrit : {dest}  ({len(ebc)} EBC)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Télécharge les EBC d'une commune (GPU/WFS)"
    )
    ap.add_argument("--insee", default=C.COMMUNE_INSEE if False else "07005")
    ap.add_argument("--out", default=str(DATA_ALBA))
    a = ap.parse_args()
    from pathlib import Path

    telecharger(a.insee, Path(a.out))
