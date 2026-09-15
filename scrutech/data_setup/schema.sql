-- ScruTech central store (DuckDB) — applied idempotently by core.db.connect().
-- Every product table carries aoi_id: one AOI = one partition, written with
-- core.db.replace_partition (DELETE the partition then INSERT — never orphaned rows).
-- Geometry is DuckDB GEOMETRY (spatial extension, loaded by core.db).

-- Registry: the AOIs we know about.
CREATE TABLE IF NOT EXISTS aoi (
    aoi_id      VARCHAR PRIMARY KEY,
    label       VARCHAR,
    kind        VARCHAR,            -- insee | dept | bbox | file | gdf
    geom        GEOMETRY,           -- WGS84
    bbox_wgs84  DOUBLE[],
    created_at  TIMESTAMP DEFAULT now()
);

-- Registry: what was computed, for which AOI, with which params, and where it landed.
CREATE TABLE IF NOT EXISTS product_runs (
    run_id      VARCHAR PRIMARY KEY,
    aoi_id      VARCHAR,
    pilier      VARCHAR,
    produit     VARCHAR,
    params      JSON,
    path        VARCHAR,
    created_at  TIMESTAMP DEFAULT now()
);

-- VegeVigie ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vege_commune_stats (
    aoi_id          VARCHAR,
    insee           VARCHAR,
    nom             VARCHAR,
    y0              INTEGER,
    y1              INTEGER,
    mean_sen_slope  DOUBLE,
    pct_greening    DOUBLE,
    pct_browning    DOUBLE,
    mean_anomaly    DOUBLE,
    min_vci         DOUBLE,
    geom            GEOMETRY
);

CREATE TABLE IF NOT EXISTS vege_timeline (
    aoi_id        VARCHAR,
    y0            INTEGER,
    y1            INTEGER,
    month         DATE,
    anomaly_mean  DOUBLE
);

-- PAF ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paf_interface_stats (
    aoi_id              VARCHAR,
    contact_m           DOUBLE,
    interface_length_m  DOUBLE,
    interface_zone_ha   DOUBLE,
    bati_area_ha        DOUBLE
);

-- Mini data centers -------------------------------------------------------
CREATE TABLE IF NOT EXISTS dc_parcelles (
    aoi_id              VARCHAR,
    id_parcelle         VARCHAR,
    insee               VARCHAR,
    score_foncier       DOUBLE,
    score_nuisances     DOUBLE,
    score_fibre         DOUBLE,
    score_energie       DOUBLE,
    score_environnement DOUBLE,
    score_total         DOUBLE,
    classe              VARCHAR,
    h3_res8             VARCHAR,
    geom                GEOMETRY
);

CREATE TABLE IF NOT EXISTS dc_heatmap (
    aoi_id           VARCHAR,
    h3_res8          VARCHAR,
    count_eligibles  INTEGER,
    count_premium    INTEGER,
    avg_score        DOUBLE,
    geom             GEOMETRY
);

-- SDBPi -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sdbpi_batiments (
    aoi_id            VARCHAR,
    id_bati           VARCHAR,
    usage_1           VARCHAR,
    surface_bati_m2   DOUBLE,
    nb_etab_actifs    INTEGER,
    statut_occupation VARCHAR,
    geom              GEOMETRY
);
