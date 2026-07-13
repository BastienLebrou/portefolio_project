"""
analyse_reelle.py — Analyse RÉELLE multi-axes sur Alba-la-Romaine (07005).

Données réelles (dossier Data_alba/, EPSG:2154) :
  - commune.parquet   : contour officiel (AOI)
  - parcelles.parquet : 6 415 parcelles cadastrales
  - batiment.parquet  : bâti BD TOPO (USAGE1, NB_LOGTS, NB_ETAGES...)
  - fibre.parquet      : immeubles ARCEP + statut FTTH (telecharge_arcep.py)
  - ligne_hta.parquet : réseau HTA 20 kV (proxy d'accès énergie)
  - ebc.parquet        : Espaces Boisés Classés (telecharge_ebc.py)

Axes évalués (réels) :
  1. FONCIER       : présence d'un bâtiment résidentiel individuel + surface libre > 50 m²
  2. NUISANCES     : recul intérieur 5 m hors bâti + tirage câbles <= 15 m
  3. FIBRE         : statut FTTH du point ARCEP le plus proche (Déployé/Raccordable)
  4. ÉNERGIE (proxy): proximité au réseau HTA (à raffiner avec les postes BT + kVA)
  5. RÉGLEMENTAIRE : hors Espace Boisé Classé

⚠️ Non disponibles, donc NON intégrés au filtre 5 : périmètres ABF (Monuments
Historiques) et zones inondables PPRI. À ajouter dès que les données sont là.

Sorties : data/outputs_reel/ (candidats + couche QA + couches SIG + rapport).
"""

import sys
import json

import geopandas as gpd
from shapely import from_wkb

import config as C
from db import connect
from pipeline import setup_macros

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DATA_ALBA = C.BASE_DIR.parent / "Data_alba"
OUT = C.DATA_DIR / "outputs_reel"
SIG = OUT / "sig"

# Seuils (repris de config.py pour le métier, + proxy HTA local)
SURF_LIBRE_MIN = C.SURFACE_LIBRE_MIN_M2     # 50 m²
BUFFER = C.BUFFER_NUISANCE_M                # 5 m
USABLE_MIN = C.BUFFER_USABLE_MIN_M2         # 4 m²
DIST_BATI_MAX = C.DIST_MAX_BATIMENT_M       # 15 m
FONCIER_REF = C.SCORE_FONCIER_REF_M2        # 400 m² -> score foncier max
K_FIBRE = C.H3_DISK_K["fibre"]              # rayon H3 recherche fibre
DIST_HTA_MAX = 150.0                        # proxy énergie (médiane commune)
AXE = 20.0
PREMIUM_MIN, BON_MIN = 80.0, 60.0


# Couleurs du style QGIS (catégorisé sur etape_rejet)
ETAPE_COULEURS = {
    "0-Candidate":     (26, 122, 58),    # vert
    "1-Foncier":       (210, 210, 210),  # gris
    "2-Nuisances":     (241, 196, 15),   # jaune
    "3-Fibre":         (230, 126, 34),   # orange
    "4-Energie (HTA)": (192, 57, 43),    # rouge
    "5-EBC":           (142, 68, 173),   # violet
}


def _wkb_gdf(con, sql, crs):
    df = con.execute(sql).fetchdf()
    return gpd.GeoDataFrame(df.drop(columns=["wkb"]),
                            geometry=from_wkb([bytes(b) for b in df["wkb"]]), crs=crs)


def _ecrire_qml(path):
    """Génère un style QGIS (.qml) catégorisé sur 'etape_rejet'.
    Posé à côté du .parquet de même nom, QGIS l'applique automatiquement."""
    cats, syms = [], []
    for i, (val, (r, g, b)) in enumerate(ETAPE_COULEURS.items()):
        cats.append(f'<category render="true" value="{val}" symbol="{i}" label="{val}"/>')
        syms.append(
            f'<symbol type="fill" name="{i}" alpha="1" clip_to_extent="1" force_rhr="0">'
            f'<layer class="SimpleFill" enabled="1" locked="0" pass="0">'
            f'<prop k="color" v="{r},{g},{b},255"/>'
            f'<prop k="outline_color" v="60,60,60,180"/>'
            f'<prop k="outline_width" v="0.1"/><prop k="outline_style" v="solid"/>'
            f'<prop k="style" v="solid"/></layer></symbol>')
    qml = (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.28" styleCategories="Symbology">\n'
        ' <renderer-v2 attr="etape_rejet" type="categorizedSymbol" forceraster="0" '
        'symbollevels="0" enableorderby="0">\n'
        f'  <categories>{"".join(cats)}</categories>\n'
        f'  <symbols>{"".join(syms)}</symbols>\n'
        " </renderer-v2>\n <layerGeometryType>2</layerGeometryType>\n</qgis>\n")
    path.write_text(qml, encoding="utf-8")


def run():
    raw = str(DATA_ALBA).replace("\\", "/")
    SIG.mkdir(parents=True, exist_ok=True)
    con = connect()
    setup_macros(con)        # macro h3_of(geom, res)

    # ===================== STAGING =====================
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.aoi AS
        SELECT ST_MakeValid(geometry) AS geom FROM read_parquet('{raw}/commune.parquet');
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.parcelles AS
        SELECT
            CAST(commune AS VARCHAR)||'-'||section||'-'||CAST(numero AS VARCHAR) AS id_parcelle,
            section, numero,
            ST_MakeValid(p.geometry) AS geom,
            ST_Area(p.geometry)      AS aire_m2,
            h3_of(p.geometry, {C.H3_RES_JOIN})    AS h3_res9,
            h3_of(p.geometry, {C.H3_RES_HEATMAP}) AS h3_res8
        FROM read_parquet('{raw}/parcelles.parquet') p, staging.aoi a
        WHERE ST_Area(p.geometry) > 0 AND ST_Intersects(p.geometry, a.geom);
    """)
    # Bâti : résidentiel = USAGE1 'Résidentiel' ; immeuble = collectif (>4 logts ou >=4 étages)
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.batiments AS
        SELECT
            ID AS id_batiment,
            (USAGE1 = 'Résidentiel') AS est_residentiel,
            (COALESCE(TRY_CAST(NB_LOGTS AS DOUBLE), 0) > 4
             OR COALESCE(TRY_CAST(NB_ETAGES AS DOUBLE), 0) >= 4) AS est_immeuble,
            ST_MakeValid(geometry) AS geom,
            h3_of(geometry, {C.H3_RES_JOIN}) AS h3_res9
        FROM read_parquet('{raw}/batiment.parquet')
        WHERE ETAT = 'En service';
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE staging.fibre AS
        SELECT id_locale, statut_deploiement, operateur, geometry AS geom,
               h3_of(geometry, {C.H3_RES_JOIN}) AS h3_res9
        FROM read_parquet('{raw}/fibre.parquet');
    """)
    con.execute(f"CREATE OR REPLACE TABLE staging.hta AS SELECT ST_MakeValid(geometry) AS geom FROM read_parquet('{raw}/ligne_hta.parquet');")
    con.execute(f"CREATE OR REPLACE TABLE staging.ebc AS SELECT ST_MakeValid(geometry) AS geom FROM read_parquet('{raw}/ebc.parquet');")

    # ===================== INTERMEDIATE =====================
    # Parcelle <-> bâti (préfiltre H3 + intersection exacte)
    con.execute(f"""
        CREATE OR REPLACE TABLE intermediate.parc_bati AS
        WITH paires AS (
            SELECT p.id_parcelle, b.est_residentiel, b.est_immeuble,
                   ST_Intersection(p.geom, b.geom) AS inter
            FROM staging.parcelles p
            JOIN staging.batiments b
              ON list_contains(h3_grid_disk(p.h3_res9, 1), b.h3_res9)
             AND ST_Intersects(p.geom, b.geom)
        )
        SELECT id_parcelle,
            COUNT(*) FILTER (WHERE est_residentiel AND NOT est_immeuble) AS n_resid_indiv,
            COUNT(*) FILTER (WHERE est_residentiel AND est_immeuble)     AS n_immeuble,
            SUM(ST_Area(inter))  AS emprise_m2,
            ST_Union_Agg(inter)  AS geom_bati
        FROM paires GROUP BY id_parcelle;
    """)
    # Fibre la plus proche (statut)
    con.execute(f"""
        CREATE OR REPLACE TABLE intermediate.fibre_proche AS
        WITH cand AS (
            SELECT p.id_parcelle, f.statut_deploiement AS statut, ST_Distance(p.geom, f.geom) AS d
            FROM staging.parcelles p
            JOIN staging.fibre f ON list_contains(h3_grid_disk(p.h3_res9, {K_FIBRE}), f.h3_res9)
        )
        SELECT id_parcelle, arg_min(statut, d) AS fibre_statut, MIN(d) AS dist_fibre_m
        FROM cand GROUP BY id_parcelle;
    """)
    # Distance au réseau HTA
    con.execute("""
        CREATE OR REPLACE TABLE intermediate.hta_proche AS
        SELECT p.id_parcelle, MIN(ST_Distance(p.geom, h.geom)) AS dist_hta_m
        FROM staging.parcelles p, staging.hta h GROUP BY p.id_parcelle;
    """)
    # Intersection EBC
    con.execute("""
        CREATE OR REPLACE TABLE intermediate.en_ebc AS
        SELECT DISTINCT p.id_parcelle
        FROM staging.parcelles p JOIN staging.ebc e ON ST_Intersects(p.geom, e.geom);
    """)

    # ===================== ÉVALUATION (5 axes) =====================
    con.execute(f"""
        CREATE OR REPLACE TABLE marts.evaluation AS
        WITH base AS (
            SELECT p.*,
                COALESCE(pb.n_resid_indiv, 0) AS n_resid_indiv,
                COALESCE(pb.n_immeuble, 0)    AS n_immeuble,
                COALESCE(pb.emprise_m2, 0)    AS emprise_m2,
                pb.geom_bati,
                p.aire_m2 - COALESCE(pb.emprise_m2, 0) AS surface_libre_m2,
                fp.fibre_statut, hp.dist_hta_m,
                (eb.id_parcelle IS NOT NULL) AS dans_ebc
            FROM staging.parcelles p
            LEFT JOIN intermediate.parc_bati   pb USING (id_parcelle)
            LEFT JOIN intermediate.fibre_proche fp USING (id_parcelle)
            LEFT JOIN intermediate.hta_proche  hp USING (id_parcelle)
            LEFT JOIN intermediate.en_ebc      eb USING (id_parcelle)
        ),
        mes AS (
            SELECT *,
                ST_Difference(ST_Buffer(geom, -{BUFFER}),
                              COALESCE(geom_bati, ST_GeomFromText('POLYGON EMPTY'))) AS geom_install
            FROM base
        ),
        ev AS (
            SELECT *,
                ST_Area(geom_install) AS install_m2,
                ST_Distance(ST_Centroid(geom_install),
                            COALESCE(geom_bati, geom)) AS dist_bati_m
            FROM mes
        )
        SELECT * EXCLUDE (geom_install, geom_bati),
            -- gates
            (n_resid_indiv > 0 AND n_immeuble = 0 AND surface_libre_m2 > {SURF_LIBRE_MIN}) AS pass_foncier,
            (install_m2 >= {USABLE_MIN} AND dist_bati_m <= {DIST_BATI_MAX})                AS pass_nuisances,
            (fibre_statut IN ('{"','".join(C.FIBRE_STATUTS_OK)}'))                          AS pass_fibre,
            (dist_hta_m <= {DIST_HTA_MAX})                                                  AS pass_energie,
            (NOT dans_ebc)                                                                  AS pass_reglement,
            -- scores (0..20 par axe)
            {AXE} * LEAST(surface_libre_m2 / {FONCIER_REF}, 1.0)                            AS score_foncier,
            LEAST(10.0 * LEAST(install_m2/40.0,1.0)
                  + CASE WHEN dist_bati_m <= {DIST_BATI_MAX} THEN 10.0 ELSE 0.0 END, {AXE}) AS score_nuisances,
            CASE fibre_statut WHEN 'Déployé' THEN {AXE} WHEN 'Raccordable' THEN 12.0 ELSE 0.0 END AS score_fibre,
            {AXE} * GREATEST(({DIST_HTA_MAX} - dist_hta_m)/{DIST_HTA_MAX}, 0.0)             AS score_energie,
            CASE WHEN dans_ebc THEN 0.0 ELSE {AXE} END                                      AS score_reglement
        FROM ev;
    """)

    # Synthèse : éligibilité, indice, classe, motif de rejet
    con.execute(f"""
        CREATE OR REPLACE TABLE marts.parcelles_qa_reel AS
        SELECT
            id_parcelle, section, numero, geom, h3_res8,
            ROUND(aire_m2,1) AS aire_m2, ROUND(surface_libre_m2,1) AS surface_libre_m2,
            n_resid_indiv, n_immeuble, fibre_statut,
            ROUND(dist_hta_m,1) AS dist_hta_m, dans_ebc,
            pass_foncier, pass_nuisances, pass_fibre, pass_energie, pass_reglement,
            (pass_foncier AND pass_nuisances AND pass_fibre AND pass_energie AND pass_reglement) AS eligible,
            ROUND(score_foncier,1) AS score_foncier, ROUND(score_nuisances,1) AS score_nuisances,
            ROUND(score_fibre,1) AS score_fibre, ROUND(score_energie,1) AS score_energie,
            ROUND(score_reglement,1) AS score_reglement,
            LEAST(ROUND(score_foncier+score_nuisances+score_fibre+score_energie+score_reglement,1),100) AS indice,
            CASE
                WHEN NOT pass_foncier    THEN '1-Foncier'
                WHEN NOT pass_nuisances  THEN '2-Nuisances'
                WHEN NOT pass_fibre      THEN '3-Fibre'
                WHEN NOT pass_energie    THEN '4-Energie (HTA)'
                WHEN NOT pass_reglement  THEN '5-EBC'
                ELSE '0-Candidate'
            END AS etape_rejet,
            CASE
                WHEN NOT (pass_foncier AND pass_nuisances AND pass_fibre AND pass_energie AND pass_reglement) THEN NULL
                WHEN score_foncier+score_nuisances+score_fibre+score_energie+score_reglement >= {PREMIUM_MIN} THEN 'Premium'
                WHEN score_foncier+score_nuisances+score_fibre+score_energie+score_reglement >= {BON_MIN}     THEN 'Bon'
                ELSE 'Moyen'
            END AS classe
        FROM marts.evaluation;
    """)

    con.execute("""
        CREATE OR REPLACE TABLE marts.heatmap_reel AS
        SELECT h3_res8, ST_GeomFromText(h3_cell_to_boundary_wkt(h3_res8)) AS geom_wgs84,
               COUNT(*) FILTER (WHERE eligible) AS nb_candidats,
               COUNT(*) FILTER (WHERE classe='Premium') AS nb_premium,
               ROUND(AVG(indice) FILTER (WHERE eligible),1) AS indice_moyen
        FROM marts.parcelles_qa_reel GROUP BY h3_res8
        HAVING COUNT(*) FILTER (WHERE eligible) > 0;
    """)

    # ===================== EXPORTS =====================
    # GeoPackage unique pour QGIS (toutes les couches en un fichier)
    gpkg = OUT / "alba_analyse.gpkg"
    if gpkg.exists():
        gpkg.unlink()

    def _bundle(gdf, layer):
        gdf.to_file(gpkg, layer=layer, driver="GPKG")

    # Candidats (éligibles) : parquet + geojson + csv + gpkg
    cand = _wkb_gdf(con, """
        SELECT id_parcelle, section, numero, aire_m2, surface_libre_m2, fibre_statut,
               dist_hta_m, score_foncier, score_nuisances, score_fibre, score_energie,
               score_reglement, indice, classe, ST_AsWKB(geom) AS wkb
        FROM marts.parcelles_qa_reel WHERE eligible ORDER BY indice DESC
    """, C.CRS_METRIQUE)
    cand.to_parquet(OUT / "candidats_reel.parquet", index=False)
    cand.to_crs(C.CRS_GEO).to_file(OUT / "candidats_reel.geojson", driver="GeoJSON")
    cand.drop(columns="geometry").to_csv(OUT / "candidats_reel.csv", index=False, encoding="utf-8-sig")
    _bundle(cand, "candidats")

    # Couche de contrôle QA (toutes les parcelles) : parquet (+ style QML auto) + gpkg
    qa = _wkb_gdf(con, """SELECT id_parcelle, aire_m2, surface_libre_m2, n_resid_indiv, n_immeuble,
        fibre_statut, dist_hta_m, dans_ebc, pass_foncier, pass_nuisances, pass_fibre, pass_energie,
        pass_reglement, eligible, indice, classe, etape_rejet, ST_AsWKB(geom) AS wkb
        FROM marts.parcelles_qa_reel""", C.CRS_METRIQUE)
    qa.to_parquet(SIG / "parcelles_qa_reel.parquet", index=False)
    _ecrire_qml(SIG / "parcelles_qa_reel.qml")          # style appliqué auto par QGIS
    _bundle(qa, "parcelles_qa")

    # Couches de contexte
    for nom, sql, crs in [
        ("commune", "SELECT ST_AsWKB(geom) AS wkb FROM staging.aoi", C.CRS_METRIQUE),
        ("batiments", "SELECT id_batiment, est_residentiel, est_immeuble, ST_AsWKB(geom) AS wkb FROM staging.batiments", C.CRS_METRIQUE),
        ("fibre", "SELECT id_locale, statut_deploiement, ST_AsWKB(geom) AS wkb FROM staging.fibre", C.CRS_METRIQUE),
        ("ligne_hta", "SELECT ST_AsWKB(geom) AS wkb FROM staging.hta", C.CRS_METRIQUE),
        ("ebc", "SELECT ST_AsWKB(geom) AS wkb FROM staging.ebc", C.CRS_METRIQUE),
        ("heatmap_reel", "SELECT h3_res8, nb_candidats, nb_premium, indice_moyen, ST_AsWKB(geom_wgs84) AS wkb FROM marts.heatmap_reel", C.CRS_GEO),
    ]:
        g = _wkb_gdf(con, sql, crs)
        g.to_parquet(SIG / f"{nom}.parquet", index=False)
        _bundle(g, nom)
    print(f"  GeoPackage QGIS : {gpkg}")

    # ===================== RAPPORT + AFFICHAGE =====================
    total = con.execute("SELECT COUNT(*) FROM marts.parcelles_qa_reel").fetchone()[0]
    rejets = con.execute("SELECT etape_rejet, COUNT(*) FROM marts.parcelles_qa_reel GROUP BY 1 ORDER BY 1").fetchall()
    classes = con.execute("SELECT classe, COUNT(*), ROUND(AVG(indice),1) FROM marts.parcelles_qa_reel WHERE eligible GROUP BY 1 ORDER BY 3 DESC").fetchall()
    nb_elig = con.execute("SELECT COUNT(*) FROM marts.parcelles_qa_reel WHERE eligible").fetchone()[0]

    rapport = {
        "commune": "Alba-la-Romaine (07005 / 07400)",
        "axes_reels": ["1-Foncier (bati BD TOPO)", "2-Nuisances", "3-Fibre (ARCEP)",
                       "4-Energie (proxy proximite HTA)", "5-Reglementaire (EBC seulement)"],
        "axes_manquants": ["ABF (Monuments Historiques)", "PPRI (zones inondables)", "capacite BT Enedis (kVA)"],
        "parcelles_total": total, "candidats": nb_elig,
        "repartition_rejet": {k: v for k, v in rejets},
        "classes": {k: {"n": v, "indice_moyen": s} for k, v, s in classes},
    }
    (OUT / "rapport_reel.json").write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 58)
    print("  ANALYSE RÉELLE MULTI-AXES — Alba-la-Romaine (07005)")
    print("=" * 58)
    print(f"  Parcelles analysées : {total}")
    print(f"  Axes RÉELS : foncier (bâti) + nuisances + fibre + énergie(HTA) + EBC")
    print(f"  Manquants  : ABF, PPRI, capacité BT (kVA)")
    print("\n  ENTONNOIR (motif du 1er rejet)")
    print("  " + "-" * 52)
    for k, v in rejets:
        print(f"  {k:<22} {v:>5}  {100*v/total:5.1f}%")
    print("  " + "-" * 52)
    print(f"  => CANDIDATS RÉELS : {nb_elig}")
    print("\n  CLASSEMENT")
    print("  " + "-" * 52)
    for cl, n, s in classes:
        print(f"  {cl:<10} {n:>5}   indice moyen {s}")
    print(f"\n  Livrables -> data/outputs_reel/ (+ sig/ pour QGIS)")
    con.close()
    return rapport


if __name__ == "__main__":
    run()
