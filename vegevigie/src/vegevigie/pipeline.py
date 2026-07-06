"""Programmatic, UI-agnostic pipeline orchestrator.

This is the single engine that both the Typer CLI and the ScruTech QGIS plugin
drive — no ``typer`` / ``qgis`` imports here, only the pure stage modules
(CLAUDE.md §11). Given an area of interest and a time window it runs
search → datacube → NDVI → monthly composites → trend → drought, and optionally
zonal aggregation, writing GeoTIFF / GeoParquet outputs that any GIS can open.

Progress is reported through a simple ``callback(percent, message)`` so a caller
(a QGIS ``QgsProcessingFeedback``, a CLI spinner, a notebook) can surface it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from vegevigie.config import Settings, load_settings

if TYPE_CHECKING:
    import geopandas as gpd
    import xarray as xr

logger = logging.getLogger("vegevigie")

# progress(percent 0-100, human message)
ProgressCallback = Callable[[int, str], None]

BBox = tuple[float, float, float, float]


def _noop(_percent: int, _message: str) -> None:
    pass


def build_settings(
    bbox: BBox,
    start_year: int,
    end_year: int,
    *,
    resolution: int | None = None,
    max_cloud_cover: float | None = None,
    data_dir: Path | None = None,
    base: Settings | None = None,
) -> Settings:
    """Build a :class:`Settings` for an arbitrary AOI/window, overriding defaults.

    ``bbox`` is WGS84 (min_lon, min_lat, max_lon, max_lat) — e.g. a QGIS extent
    reprojected to EPSG:4326. Everything not overridden falls back to
    ``config/default.yaml`` (or ``base`` if given).
    """
    settings = base or load_settings()
    payload = settings.model_dump()
    payload["aoi"]["small_bbox"] = list(bbox)
    payload["time"] = {"start": start_year, "end": end_year}
    if resolution is not None:
        payload["raster"]["resolution"] = resolution
    if max_cloud_cover is not None:
        payload["stac"]["max_cloud_cover"] = max_cloud_cover
    if data_dir is not None:
        payload["paths"]["data_dir"] = str(data_dir)
    return Settings.model_validate(payload)


@dataclass
class PipelineResult:
    """Outputs of a pipeline run; ``*_path`` fields are set as stages complete."""

    settings: Settings
    trend_tif: Path | None = None
    drought_tif: Path | None = None
    zonal_parquet: Path | None = None
    duckdb_path: Path | None = None
    timeline_parquet: Path | None = None
    scene_count: int = 0
    written: list[Path] = field(default_factory=list)


def _write_band(da: xr.DataArray, crs: object, path: Path, name: str) -> Path:
    """Write a single 2D DataArray to a GeoTIFF with an explicit CRS + band name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    band = da.rio.write_crs(crs)
    band.rio.to_raster(path)
    logger.info("Wrote %s -> %s", name, path)
    return path


def run_pipeline(
    settings: Settings,
    *,
    zones: gpd.GeoDataFrame | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> PipelineResult:
    """Run search → cube → NDVI → composites → trend → drought (+ optional zonal).

    Needs outbound access to the STAC provider (Planetary Computer). ``zones`` (a
    polygon layer, e.g. communes) enables zonal aggregation + DuckDB ranking.
    Returns a :class:`PipelineResult` with the written output paths.
    """
    report = progress or _noop

    # Imported here so the module (and QGIS plugin load) don't pay for the heavy
    # datacube stack until an analysis actually runs.
    import rioxarray  # noqa: F401 — registers the .rio accessor used below

    from vegevigie.catalog import (
        PlanetaryComputerBackend,
        build_search_params,
        search_and_cache,
    )
    from vegevigie.composite import build_monthly_ndvi
    from vegevigie.datacube import build_cube
    from vegevigie.drought import drought_dataset, drought_timeline
    from vegevigie.indices import masked_ndvi
    from vegevigie.trend import trend_dataset

    bbox: BBox = settings.aoi.small_bbox
    start, end = settings.time.start, settings.time.end
    result = PipelineResult(settings=settings)
    backend = PlanetaryComputerBackend()

    report(5, f"Searching Sentinel-2 scenes {start}–{end}…")
    params = build_search_params(
        bbox=bbox,
        start_year=start,
        end_year=end,
        collection=settings.stac.collection,
        max_cloud_cover=settings.stac.max_cloud_cover,
    )
    items_path = settings.paths.raw / f"items_{start}_{end}.json"
    items = search_and_cache(backend, params, items_path, force=force)
    result.scene_count = len(items)
    if not items:
        report(100, "No scenes found for this AOI/window.")
        return result

    report(25, f"Building datacube from {len(items)} scenes at {settings.raster.resolution} m…")
    cube = build_cube(
        backend=backend,
        item_dicts=items,
        bbox=bbox,
        resolution=settings.raster.resolution,
        chunk_size=settings.raster.chunk_size,
    )
    crs = cube.rio.crs
    if crs is None and hasattr(cube, "odc"):
        crs = cube.odc.geobox.crs  # odc-stac always attaches a geobox

    report(45, "Cloud-masking + NDVI + monthly composites…")
    ndvi = masked_ndvi(cube["red"], cube["nir"], cube["scl"]).rename("ndvi")
    monthly = build_monthly_ndvi(ndvi, fill_max_gap=settings.composite.fill_max_gap).compute()

    report(65, "Per-pixel Mann-Kendall + Sen's slope…")
    trend = trend_dataset(
        monthly, alpha=settings.trend.p_value, min_valid=settings.trend.min_valid_months
    ).compute()
    result.trend_tif = _write_band(
        trend["sen_slope"],
        crs,
        settings.paths.processed / f"trend_sen_slope_{start}_{end}.tif",
        "sen_slope",
    )
    _write_band(
        trend["trend_class"],
        crs,
        settings.paths.processed / f"trend_class_{start}_{end}.tif",
        "trend_class",
    )

    report(80, "Drought anomaly + VCI…")
    drought = drought_dataset(monthly).compute()
    mean_anomaly = drought["ndvi_anomaly"].mean("time")
    min_vci = drought["vci"].min("time")
    result.drought_tif = _write_band(
        mean_anomaly,
        crs,
        settings.paths.processed / f"drought_anomaly_{start}_{end}.tif",
        "mean_anomaly",
    )
    timeline = drought_timeline(drought["ndvi_anomaly"]).compute()
    result.timeline_parquet = settings.paths.processed / f"drought_timeline_{start}_{end}.parquet"
    timeline.to_dataframe().reset_index().to_parquet(result.timeline_parquet)

    if zones is not None and len(zones):
        report(92, f"Zonal aggregation over {len(zones)} zones…")
        result.zonal_parquet, result.duckdb_path = _run_zonal(
            settings, zones, trend, mean_anomaly, min_vci, start, end
        )

    result.written = [
        p
        for p in (
            result.trend_tif,
            result.drought_tif,
            result.zonal_parquet,
            result.timeline_parquet,
        )
        if p is not None
    ]
    report(100, f"Done — {len(result.written)} outputs written.")
    return result


def _run_zonal(
    settings: Settings,
    zones: gpd.GeoDataFrame,
    trend: xr.Dataset,
    mean_anomaly: xr.DataArray,
    min_vci: xr.DataArray,
    start: int,
    end: int,
) -> tuple[Path, Path]:
    from vegevigie.store import write_duckdb, write_geoparquet
    from vegevigie.zonal import commune_stats

    stats = commune_stats(
        zones,
        sen_slope=trend["sen_slope"],
        trend_class=trend["trend_class"],
        mean_anomaly=mean_anomaly,
        min_vci=min_vci,
    )
    parquet = settings.paths.processed / f"zonal_stats_{start}_{end}.parquet"
    duckdb_path = settings.paths.processed / "vegevigie.duckdb"
    write_geoparquet(stats, parquet)
    write_duckdb(stats.drop(columns="geometry"), duckdb_path, table="commune_stats")
    return parquet, duckdb_path
