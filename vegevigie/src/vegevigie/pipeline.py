"""Programmatic, UI-agnostic pipeline orchestrator.

This is the single engine that both the Typer CLI and the ScruTech QGIS plugin
drive — no ``typer`` / ``qgis`` imports here (CLAUDE.md §11). Since the S1
"engine spine" refactor (qgis_plugin/ROADMAP.md §4) the actual work lives in
:mod:`vegevigie.stages`: idempotent stage functions with file contracts, tied
together by a run manifest. :func:`run_pipeline` is now a thin composition of
those stages — re-running with unchanged parameters reuses every artifact that
is already on disk instead of recomputing it.

Progress is reported through a simple ``callback(percent, message)`` so a caller
(a QGIS ``QgsProcessingFeedback``, a CLI spinner, a notebook) can surface it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from vegevigie.config import Settings, load_settings
from vegevigie.stages import (
    ProgressCallback,
    RunContext,
    RunManifest,
    stage_composites,
    stage_drought,
    stage_search,
    stage_trend,
    stage_zonal,
)

if TYPE_CHECKING:
    import geopandas as gpd

    from vegevigie.catalog import StacBackend

logger = logging.getLogger("vegevigie")

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
    trend_class_tif: Path | None = None
    pvalue_tif: Path | None = None
    drought_tif: Path | None = None
    vci_tif: Path | None = None
    zonal_parquet: Path | None = None
    zonal_gpkg: Path | None = None
    duckdb_path: Path | None = None
    timeline_parquet: Path | None = None
    scene_count: int = 0
    written: list[Path] = field(default_factory=list)


def run_pipeline(
    settings: Settings,
    *,
    zones: gpd.GeoDataFrame | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
    backend: StacBackend | None = None,
) -> PipelineResult:
    """Run search → composites → trend → drought (+ optional zonal), stage by stage.

    Needs outbound access to the STAC provider (Planetary Computer) unless every
    stage is already cached in the run folder. ``zones`` (a polygon layer, e.g.
    communes) enables zonal aggregation + DuckDB ranking. Returns a
    :class:`PipelineResult` with the written output paths.
    """
    report = progress or _noop
    manifest = RunManifest.for_settings(settings)
    ctx = RunContext(settings=settings, manifest=manifest, force=force, progress=report)
    result = PipelineResult(settings=settings)

    search_out = stage_search(ctx.scoped(2, 15), backend=backend)
    result.scene_count = int(search_out.meta.get("scene_count", 0))
    if result.scene_count == 0:
        report(100, "No scenes found for this AOI/window.")
        return result

    stage_composites(ctx.scoped(15, 60), backend=backend)

    trend_out = stage_trend(ctx.scoped(60, 78))
    result.trend_tif = trend_out.artifacts.get("sen_slope")
    result.trend_class_tif = trend_out.artifacts.get("trend_class")
    result.pvalue_tif = trend_out.artifacts.get("mk_pvalue")

    drought_out = stage_drought(ctx.scoped(78, 90))
    result.drought_tif = drought_out.artifacts.get("anomaly")
    result.vci_tif = drought_out.artifacts.get("min_vci")
    result.timeline_parquet = drought_out.artifacts.get("timeline")

    if zones is not None and len(zones):
        zonal_out = stage_zonal(ctx.scoped(90, 98), zones)
        result.zonal_parquet = zonal_out.artifacts.get("stats_parquet")
        result.zonal_gpkg = zonal_out.artifacts.get("stats_gpkg")
        result.duckdb_path = zonal_out.artifacts.get("duckdb")

    result.written = [
        p
        for p in (
            result.trend_tif,
            result.trend_class_tif,
            result.pvalue_tif,
            result.drought_tif,
            result.vci_tif,
            result.timeline_parquet,
            result.zonal_parquet,
            result.zonal_gpkg,
        )
        if p is not None
    ]
    report(100, f"Done — {len(result.written)} outputs written.")
    return result
