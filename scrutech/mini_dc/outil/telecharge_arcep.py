"""
telecharge_arcep.py — Télécharge les données fibre ARCEP "Ma connexion internet"
pour une commune, et produit une couche de points immeubles avec leur statut
de déploiement fibre (FTTH).

Sources (open data ARCEP, https://data.arcep.fr/fixe/maconnexioninternet/) :
  - base_imb/last/departement/base_imb_{dept}.csv.gz
        localisation des immeubles (imb_x/imb_y en EPSG:3857, type PA/IM, INSEE)
  - eligibilite/last/departement/actuel_{dept}.csv.gz
        technologies disponibles par immeuble (code_techno = 'FO' => fibre)

Logique : un immeuble est "Déployé" (FTTH) s'il possède au moins une ligne
d'éligibilité avec code_techno = 'FO'. Sinon "Non desservi" (cuivre/autre).

Sortie : Data_alba/fibre.parquet (GeoParquet, EPSG:2154), prête pour l'analyse.
Colonnes : id_locale, statut_deploiement, operateur, imb_type, nb_logements.

Usage :
    python telecharge_arcep.py                       # Alba (07005), dept 07
    python telecharge_arcep.py --dept 07 --insee 07005
"""

import sys
import argparse
import tempfile
import urllib.request
from pathlib import Path

import pandas as pd
import geopandas as gpd

import config as C

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "https://data.arcep.fr/fixe/maconnexioninternet"
URL_IMB = BASE + "/base_imb/last/departement/base_imb_{dept}.csv.gz"
URL_ELIG = BASE + "/eligibilite/last/departement/actuel_{dept}.csv.gz"
DATA_ALBA = C.BASE_DIR.parent / "Data_alba"
CRS_ARCEP = 3857           # imb_x / imb_y sont en Web Mercator
UA = {"User-Agent": "data-center-sig/1.0 (projet perso)"}


def _telecharger(url: str, dest: Path) -> Path:
    """Télécharge un fichier (avec User-Agent) vers un chemin local."""
    print(f"  téléchargement {url.split('/')[-1]} ...")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        f.write(r.read())
    print(f"    {dest.stat().st_size/1e6:.1f} Mo")
    return dest


def telecharger(dept: str, insee: str, out_dir: Path) -> None:
    print(f"ARCEP fibre — commune {insee} (dept {dept})")
    tmp = Path(tempfile.mkdtemp(prefix="arcep_"))

    # 1) Base immeuble -> on garde la commune voulue
    f_imb = _telecharger(URL_IMB.format(dept=dept), tmp / "imb.csv.gz")
    imb = pd.read_csv(f_imb, sep=";", dtype=str, compression="gzip",
                      usecols=["imb_id", "imb_x", "imb_y", "imb_code_insee",
                               "imb_type", "imb_nbr_logloc"])
    imb = imb[imb["imb_code_insee"] == insee].copy()
    print(f"  immeubles dans la commune : {len(imb)}")
    if imb.empty:
        print("  (aucun immeuble — vérifier le code INSEE)")
        return
    ids = set(imb["imb_id"])

    # 2) Éligibilité -> présence de la fibre (FO) par immeuble de la commune
    f_el = _telecharger(URL_ELIG.format(dept=dept), tmp / "elig.csv.gz")
    elig = pd.read_csv(f_el, sep=";", dtype=str, compression="gzip",
                       usecols=["imb_id", "code_techno", "code_operateur"])
    elig = elig[elig["imb_id"].isin(ids)]
    fo = elig[elig["code_techno"] == "FO"]
    imb_fo = set(fo["imb_id"])
    # opérateur fibre principal par immeuble (le premier rencontré)
    op_fo = fo.groupby("imb_id")["code_operateur"].first().to_dict()
    print(f"  immeubles avec fibre (FO) : {len(imb_fo)} / {len(imb)}")

    # 3) Construction de la couche de points (EPSG:3857 -> 2154)
    imb["statut_deploiement"] = imb["imb_id"].apply(
        lambda i: "Déployé" if i in imb_fo else "Non desservi")
    imb["operateur"] = imb["imb_id"].map(op_fo).fillna("")
    imb["nb_logements"] = pd.to_numeric(imb["imb_nbr_logloc"], errors="coerce")
    gdf = gpd.GeoDataFrame(
        imb.rename(columns={"imb_id": "id_locale"}),
        geometry=gpd.points_from_xy(pd.to_numeric(imb["imb_x"]),
                                    pd.to_numeric(imb["imb_y"])),
        crs=CRS_ARCEP,
    ).to_crs(C.CRS_METRIQUE)

    out_dir.mkdir(parents=True, exist_ok=True)
    cols = ["id_locale", "statut_deploiement", "operateur", "imb_type", "nb_logements"]
    gdf = gdf[cols + ["geometry"]]
    dest = out_dir / "fibre.parquet"
    gdf.to_parquet(dest, index=False)
    n_dep = (gdf["statut_deploiement"] == "Déployé").sum()
    print(f"  écrit : {dest}  ({len(gdf)} immeubles, {n_dep} fibrés)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Télécharge les données fibre ARCEP d'une commune")
    ap.add_argument("--dept", default="07")
    ap.add_argument("--insee", default="07005")
    ap.add_argument("--out", default=str(DATA_ALBA))
    a = ap.parse_args()
    telecharger(a.dept, a.insee, Path(a.out))
