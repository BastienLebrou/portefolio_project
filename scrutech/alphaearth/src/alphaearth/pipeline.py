"""AOI-only AlphaEarth change detection — study area + two years in, change map out.

CE QUE ÇA FAIT : à partir d'une **emprise** et de **deux années**, calcule (côté Earth
Engine) la distance cosine entre les empreintes AlphaEarth, marque les pixels qui ont
vraiment changé, et écrit une couche GeoParquet + GeoJSON prête pour QGIS/WebGIS.

Aucune donnée à fournir : les embeddings viennent de GEE. L'auth passe par
``credentials_json`` (le plugin QGIS lit QgsAuthManager et le transmet à l'interpréteur
externe via une variable d'environnement) — jamais de clé sur disque.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("alphaearth")

WGS84 = "EPSG:4326"


def detect_change_for_aoi(
    aoi_geojson: dict,
    year1: int,
    year2: int,
    out_dir: Path,
    *,
    credentials_json: str | None = None,
    percentile: float = 95.0,
    max_pixels: int = 500_000,
    progress=None,
) -> tuple[Path, Path, dict]:
    """Compute the year1→year2 cosine-change surface over the AOI and write the products.

    Returns ``(changed_parquet, all_geojson, summary)``. ``changed_parquet`` holds only the
    pixels above the ``percentile`` threshold (the change candidates); the GeoJSON carries
    every sampled pixel with its ``change_distance`` for context.
    """
    import numpy as np

    from alphaearth.change import flag_by_percentile
    from alphaearth.client import authenticate_gee, fetch_change_samples

    # `progress` est une fonction optionnelle passée par l'appelant (ex: la barre de
    # progression du plugin QGIS) pour être informé de l'avancement (pourcentage, message).
    # Si personne n'en fournit, `report` devient une fonction qui ne fait rien
    # (`lambda _pct, _msg: None`) : le reste du code peut appeler report(...) sans jamais
    # se soucier de savoir si un callback existe vraiment.
    report = progress or (lambda _pct, _msg: None)
    report(15, "Authenticating to Google Earth Engine…")
    authenticate_gee(credentials_json=credentials_json)

    report(35, f"Sampling AlphaEarth change {year1}→{year2} (server-side cosine)…")
    gdf = fetch_change_samples(aoi_geojson, year1, year2, max_pixels=max_pixels)
    if gdf.empty:
        raise RuntimeError(
            "AlphaEarth returned no pixels — check the AOI is on land and both years exist "
            "in GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL."
        )

    report(75, "Flagging changed pixels…")
    dist = gdf["change_distance"].to_numpy(dtype=float)
    changed, threshold = flag_by_percentile(dist, percentile)
    gdf["changed"] = changed

    out_dir.mkdir(parents=True, exist_ok=True)
    all_geojson = out_dir / f"alphaearth_change_{year1}_{year2}.geojson"
    changed_parquet = out_dir / f"alphaearth_change_{year1}_{year2}_candidates.parquet"
    gdf.to_file(all_geojson, driver="GeoJSON")
    gdf[gdf["changed"]].to_parquet(changed_parquet)

    summary = {
        "year1": year1,
        "year2": year2,
        "n_pixels": int(len(gdf)),
        "n_changed": int(np.count_nonzero(changed)),
        "threshold": round(threshold, 4),
        "percentile": percentile,
    }
    report(
        100, f"Change: {summary['n_changed']}/{summary['n_pixels']} pixels above p{percentile:.0f}."
    )
    logger.info("AlphaEarth change %s→%s: %s", year1, year2, summary)
    return changed_parquet, all_geojson, summary
