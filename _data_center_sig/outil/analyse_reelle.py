"""
analyse_reelle.py — Analyse RÉELLE (partielle) sur Alba-la-Romaine (07005).

Données réelles disponibles (dossier Data_alba/, EPSG:2154) :
  - commune.parquet    : contour officiel (AOI)
  - parcelles.parquet  : 6 415 parcelles cadastrales (section/numéro)
  - ligne_hta.parquet  : 112 tronçons du réseau HTA 20 kV (Enedis)

⚠️ Honnêteté méthodologique : il MANQUE le bâti (BD TOPO), la fibre (ARCEP) et
les contraintes réglementaires (ABF/PPRI/EBC). On n'évalue donc PAS les 5 filtres
du pipeline complet, mais seulement les 2 axes que la donnée réelle permet :

   AXE 1 — FONCIER  : aire réelle de la parcelle dans une fourchette "habitat".
                      (sans bâti, on ne peut pas calculer la surface LIBRE ni
                      exclure les immeubles -> on prend l'aire totale en proxy.)
   AXE 4 — ÉNERGIE  : proximité au réseau HTA (proxy d'accès au raccordement
                      d'une charge 36 kVA ; à raffiner avec les postes BT + kVA).

Les axes Nuisances / Fibre / Réglementaire sont marqués "NON ÉVALUÉ".

Sorties : data/outputs_reel/ (candidats + couche QA + couches SIG + rapport).
"""

import sys
import json

import geopandas as gpd
from shapely import from_wkb

import config as C
from db import connect

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# --- Chemins -----------------------------------------------------------------
DATA_ALBA = (C.BASE_DIR.parent / "Data_alba")
OUT = C.DATA_DIR / "outputs_reel"
SIG = OUT / "sig"
SIG.mkdir(parents=True, exist_ok=True)

# --- Seuils RÉELS (calés sur la distribution observée des données) -----------
SURF_MIN_M2 = 200.0      # exclut micro-parcelles / délaissés
SURF_MAX_M2 = 3000.0     # exclut grandes parcelles agricoles
SURF_REF_M2 = 1000.0     # aire donnant le score foncier maximal
DIST_HTA_MAX_M = 150.0   # médiane de la commune : la moitié la mieux raccordable
AXE_MAX = 20.0           # chaque axe pèse 0..20
PREMIUM_MIN, BON_MIN = 80.0, 60.0   # seuils sur l'indice 0..100


def _wkb_gdf(con, sql: str, crs: int) -> gpd.GeoDataFrame:
    df = con.execute(sql).fetchdf()
    return gpd.GeoDataFrame(df.drop(columns=["wkb"]),
                            geometry=from_wkb([bytes(b) for b in df["wkb"]]), crs=crs)


def run() -> dict:
    raw = str(DATA_ALBA).replace("\\", "/")
    con = connect()

    # ---- STAGING : on nettoie et on clippe les parcelles dans la commune ----
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.aoi AS
        SELECT ST_MakeValid(geometry) AS geom
        FROM read_parquet('{raw}/commune.parquet');
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.parcelles AS
        SELECT
            CAST(commune AS VARCHAR) || '-' || section || '-' || CAST(numero AS VARCHAR) AS id_parcelle,
            section, numero,
            ST_MakeValid(geometry) AS geom,
            ST_Area(geometry)      AS aire_m2,
            h3_latlng_to_cell(
                ST_Y(ST_Transform(ST_Centroid(geometry),'EPSG:2154','EPSG:4326',true)),
                ST_X(ST_Transform(ST_Centroid(geometry),'EPSG:2154','EPSG:4326',true)), 9) AS h3_res8
        FROM read_parquet('{raw}/parcelles.parquet') p, staging.aoi a
        WHERE ST_Area(geometry) > 0
          AND ST_Intersects(p.geometry, a.geom);
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.hta AS
        SELECT ST_MakeValid(geometry) AS geom
        FROM read_parquet('{raw}/ligne_hta.parquet');
    """)
    # h3_res8 ci-dessus est en réalité res9 ; on dérive la cellule "quartier" res8
    con.execute("ALTER TABLE staging.parcelles RENAME h3_res8 TO h3_res9;")
    con.execute("ALTER TABLE staging.parcelles ADD COLUMN h3_res8 UBIGINT;")
    con.execute("UPDATE staging.parcelles SET h3_res8 = h3_cell_to_parent(h3_res9, 8);")

    # ---- DISTANCE au réseau HTA (proxy énergie) ----------------------------
    con.execute("""
        CREATE OR REPLACE TABLE intermediate.parcelles_hta AS
        SELECT p.id_parcelle, MIN(ST_Distance(p.geom, h.geom)) AS dist_hta_m
        FROM staging.parcelles p, staging.hta h
        GROUP BY p.id_parcelle;
    """)

    # ---- ÉVALUATION : 2 axes réels + indice + classe + motif de rejet ------
    con.execute(f"""
        CREATE OR REPLACE TABLE marts.parcelles_qa_reel AS
        WITH e AS (
            SELECT p.*, d.dist_hta_m,
                (p.aire_m2 BETWEEN {SURF_MIN_M2} AND {SURF_MAX_M2})   AS pass_foncier,
                (d.dist_hta_m <= {DIST_HTA_MAX_M})                    AS pass_energie,
                {AXE_MAX} * LEAST(p.aire_m2 / {SURF_REF_M2}, 1.0)     AS score_foncier,
                {AXE_MAX} * GREATEST(({DIST_HTA_MAX_M} - d.dist_hta_m) / {DIST_HTA_MAX_M}, 0.0) AS score_energie
            FROM staging.parcelles p
            JOIN intermediate.parcelles_hta d USING (id_parcelle)
        )
        SELECT *,
            (pass_foncier AND pass_energie) AS eligible,
            ROUND((score_foncier + score_energie) / (2 * {AXE_MAX}) * 100, 1) AS indice,
            CASE
                WHEN NOT pass_foncier THEN '1-Foncier (aire)'
                WHEN NOT pass_energie THEN '4-Energie (HTA > {DIST_HTA_MAX_M:.0f}m)'
                ELSE '0-Candidate'
            END AS etape_rejet,
            CASE
                WHEN NOT (pass_foncier AND pass_energie) THEN NULL
                WHEN (score_foncier + score_energie) / (2 * {AXE_MAX}) * 100 >= {PREMIUM_MIN} THEN 'Premium'
                WHEN (score_foncier + score_energie) / (2 * {AXE_MAX}) * 100 >= {BON_MIN}     THEN 'Bon'
                ELSE 'Moyen'
            END AS classe
        FROM e;
    """)

    # ---- Heatmap quartier (H3 res8) sur les candidats ----------------------
    con.execute("""
        CREATE OR REPLACE TABLE marts.heatmap_reel AS
        SELECT h3_res8,
               ST_GeomFromText(h3_cell_to_boundary_wkt(h3_res8)) AS geom_wgs84,
               COUNT(*) FILTER (WHERE eligible) AS nb_candidats,
               COUNT(*) FILTER (WHERE classe='Premium') AS nb_premium,
               ROUND(AVG(indice) FILTER (WHERE eligible), 1) AS indice_moyen
        FROM marts.parcelles_qa_reel
        GROUP BY h3_res8
        HAVING COUNT(*) FILTER (WHERE eligible) > 0;
    """)

    # ---- EXPORTS -----------------------------------------------------------
    # Candidats (éligibles) : GeoParquet + GeoJSON + CSV
    cand = _wkb_gdf(con, """
        SELECT id_parcelle, section, numero,
               ROUND(aire_m2,1) AS aire_m2, ROUND(dist_hta_m,1) AS dist_hta_m,
               ROUND(score_foncier,1) AS score_foncier, ROUND(score_energie,1) AS score_energie,
               indice, classe, ST_AsWKB(geom) AS wkb
        FROM marts.parcelles_qa_reel WHERE eligible ORDER BY indice DESC
    """, C.CRS_METRIQUE)
    cand.to_parquet(OUT / "candidats_reel.parquet", index=False)
    cand.to_crs(C.CRS_GEO).to_file(OUT / "candidats_reel.geojson", driver="GeoJSON")
    cand.drop(columns="geometry").to_csv(OUT / "candidats_reel.csv", index=False, encoding="utf-8-sig")

    # Couche de contrôle QA : TOUTES les parcelles annotées
    qa = _wkb_gdf(con, """
        SELECT id_parcelle, section, numero, ROUND(aire_m2,1) AS aire_m2,
               ROUND(dist_hta_m,1) AS dist_hta_m, pass_foncier, pass_energie,
               eligible, indice, classe, etape_rejet, ST_AsWKB(geom) AS wkb
        FROM marts.parcelles_qa_reel
    """, C.CRS_METRIQUE)
    qa.to_parquet(SIG / "parcelles_qa_reel.parquet", index=False)

    # Contexte SIG : commune + réseau HTA
    _wkb_gdf(con, "SELECT ST_AsWKB(geom) AS wkb FROM staging.aoi", C.CRS_METRIQUE)\
        .to_parquet(SIG / "commune.parquet", index=False)
    _wkb_gdf(con, "SELECT ST_AsWKB(geom) AS wkb FROM staging.hta", C.CRS_METRIQUE)\
        .to_parquet(SIG / "ligne_hta.parquet", index=False)
    _wkb_gdf(con, "SELECT h3_res8, nb_candidats, nb_premium, indice_moyen, ST_AsWKB(geom_wgs84) AS wkb FROM marts.heatmap_reel", C.CRS_GEO)\
        .to_parquet(SIG / "heatmap_reel.parquet", index=False)

    # ---- Statistiques ------------------------------------------------------
    total = con.execute("SELECT COUNT(*) FROM marts.parcelles_qa_reel").fetchone()[0]
    rejets = con.execute("""SELECT etape_rejet, COUNT(*) FROM marts.parcelles_qa_reel
                            GROUP BY etape_rejet ORDER BY etape_rejet""").fetchall()
    classes = con.execute("""SELECT classe, COUNT(*), ROUND(AVG(indice),1) FROM marts.parcelles_qa_reel
                             WHERE eligible GROUP BY classe ORDER BY 3 DESC""").fetchall()
    nb_elig = con.execute("SELECT COUNT(*) FROM marts.parcelles_qa_reel WHERE eligible").fetchone()[0]

    rapport = {
        "commune": "Alba-la-Romaine (07005 / 07400)",
        "axes_evalues": ["1-Foncier (aire reelle)", "4-Energie (proximite HTA)"],
        "axes_non_evalues": ["2-Nuisances (pas de bati)", "3-Fibre (pas d'ARCEP)",
                             "5-Reglementaire (pas d'ABF/PPRI/EBC)"],
        "seuils": {"surface_min_m2": SURF_MIN_M2, "surface_max_m2": SURF_MAX_M2,
                   "dist_hta_max_m": DIST_HTA_MAX_M},
        "parcelles_total": total,
        "candidats": nb_elig,
        "repartition_rejet": {k: v for k, v in rejets},
        "classes": {k: {"n": v, "indice_moyen": s} for k, v, s in classes},
    }
    with open(OUT / "rapport_reel.json", "w", encoding="utf-8") as f:
        json.dump(rapport, f, ensure_ascii=False, indent=2)

    # ---- Affichage ---------------------------------------------------------
    print("=" * 56)
    print("  ANALYSE RÉELLE — Alba-la-Romaine (07005)")
    print("=" * 56)
    print(f"  Parcelles analysées : {total}")
    print(f"  Axes réels évalués  : Foncier (aire) + Énergie (HTA)")
    print(f"  Axes non évalués    : Nuisances, Fibre, Réglementaire (données absentes)")
    print("\n  ENTONNOIR (2 axes réels)")
    print("  " + "-" * 50)
    for k, v in rejets:
        pct = 100 * v / total
        print(f"  {k:<28} {v:>5}  {pct:5.1f}%")
    print("  " + "-" * 50)
    print(f"  => CANDIDATS RÉELS : {nb_elig}")
    print("\n  CLASSEMENT DES CANDIDATS")
    print("  " + "-" * 50)
    for cl, n, s in classes:
        print(f"  {cl:<10} {n:>5}   indice moyen {s}")
    print("\n  Livrables -> data/outputs_reel/ (+ sig/ pour QGIS)")
    con.close()
    return rapport


if __name__ == "__main__":
    run()
