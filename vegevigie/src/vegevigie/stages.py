"""Stage functions + run manifest — the engine spine (qgis_plugin/ROADMAP.md §4).

Every pipeline stage is an **idempotent function with a file contract**: it reads
its inputs from the run folder, writes its artifacts there, and records what it
produced in a :class:`RunManifest` (``scrutech_run.json``). Any front end — the
Typer CLI, a ScruTech Processing algorithm, a QGIS model, the dashboard — can run
one stage, resume a run, or skip work whose inputs haven't changed.

The manifest is keyed by a fingerprint of the *science* parameters (AOI, window,
resolution, thresholds — everything except output paths). When the fingerprint
matches and a stage's artifacts still exist on disk, the stage is skipped unless
``force`` is set. When the fingerprint changes, the manifest starts empty and the
stages recompute (existing files for other windows are left untouched — filenames
carry the year window).

No ``typer``/``qgis`` imports here, and the heavy datacube stack is imported
lazily inside the stage bodies so this module stays cheap to import (the QGIS
plugin loads it at startup).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from vegevigie.config import Settings

if TYPE_CHECKING:
    import geopandas as gpd
    import xarray as xr

    from vegevigie.catalog import StacBackend

logger = logging.getLogger("vegevigie")

# progress(percent 0-100, human message)
ProgressCallback = Callable[[int, str], None]

MANIFEST_NAME = "scrutech_run.json"
MANIFEST_VERSION = 1

# Stage names — shared vocabulary across CLI, qgis_runner and the ScruTech plugin.
STAGE_SEARCH = "search"
STAGE_COMPOSITES = "composites"
STAGE_TREND = "trend"
STAGE_DROUGHT = "drought"
STAGE_ZONAL = "zonal"
STAGE_RANK = "rank"
PIPELINE_STAGES = (STAGE_SEARCH, STAGE_COMPOSITES, STAGE_TREND, STAGE_DROUGHT, STAGE_ZONAL)
ALL_STAGES = (*PIPELINE_STAGES, STAGE_RANK)


class StageInputError(RuntimeError):
    """A stage's input artifact is missing — an earlier stage must run first."""


def settings_fingerprint(settings: Settings) -> str:
    """Stable hash of the parameters that determine the pipeline outputs.

    ``paths`` is excluded: *where* outputs land doesn't change *what* they are, so
    moving a run folder (or mounting it elsewhere) keeps the cache valid.
    """
    payload = settings.model_dump(mode="json")
    payload.pop("paths", None)
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class RunManifest:
    """The run ledger: which stage produced which artifacts, for which parameters."""

    path: Path
    fingerprint: str
    settings_payload: dict[str, Any]
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def for_settings(cls, settings: Settings) -> RunManifest:
        """Load the manifest of ``settings``' data dir, resetting it on parameter change."""
        data_dir = settings.paths.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / MANIFEST_NAME
        fingerprint = settings_fingerprint(settings)
        payload = settings.model_dump(mode="json")

        if path.exists():
            try:
                raw = json.loads(path.read_text())
            except (OSError, ValueError):
                logger.warning("Unreadable manifest at %s — starting fresh.", path)
                raw = None
            if (
                raw is not None
                and raw.get("version") == MANIFEST_VERSION
                and raw.get("fingerprint") == fingerprint
            ):
                return cls(path, fingerprint, payload, dict(raw.get("stages", {})))
        return cls(path, fingerprint, payload)

    def save(self) -> None:
        body = {
            "version": MANIFEST_VERSION,
            "fingerprint": self.fingerprint,
            "settings": self.settings_payload,
            "stages": self.stages,
        }
        self.path.write_text(json.dumps(body, indent=2))

    def record(
        self, stage: str, artifacts: dict[str, Path], meta: dict[str, Any] | None = None
    ) -> None:
        """Register a completed stage (and persist the manifest)."""
        self.stages[stage] = {
            "artifacts": {key: self._store_path(p) for key, p in artifacts.items()},
            "meta": meta or {},
            "completed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.save()

    def fresh(self, stage: str) -> dict[str, Path] | None:
        """Return the stage's artifacts if recorded *and* all still on disk, else None."""
        record = self.stages.get(stage)
        if record is None:
            return None
        artifacts = {key: self._load_path(s) for key, s in record.get("artifacts", {}).items()}
        if artifacts and all(p.exists() for p in artifacts.values()):
            return artifacts
        return None

    def meta(self, stage: str) -> dict[str, Any]:
        record = self.stages.get(stage)
        return dict(record.get("meta", {})) if record else {}

    # Artifacts are stored relative to the manifest's folder when they live under
    # it, so a run folder stays valid when moved/copied (e.g. from a temp dir).
    def _store_path(self, p: Path) -> str:
        base = self.path.parent.resolve()
        try:
            return (p.resolve().relative_to(base)).as_posix()
        except ValueError:
            return str(p)

    def _load_path(self, stored: str) -> Path:
        p = Path(stored)
        return p if p.is_absolute() else self.path.parent / p


def load_manifest_settings(run_folder: Path) -> Settings:
    """Rebuild the :class:`Settings` of a previous run from its manifest.

    This is how downstream stages (trend, drought, zonal, rank) — and the ScruTech
    per-stage algorithms — pick up a run folder without re-entering the AOI/window:
    the manifest carries the full settings, only ``data_dir`` is re-anchored to
    where the manifest actually is.
    """
    path = Path(run_folder) / MANIFEST_NAME
    if not path.exists():
        msg = (
            f"No run manifest ({MANIFEST_NAME}) in {run_folder} — run the 'search' "
            "stage (or the full pipeline) on this folder first."
        )
        raise StageInputError(msg)
    payload = json.loads(path.read_text())["settings"]
    payload.setdefault("paths", {})["data_dir"] = str(run_folder)
    return Settings.model_validate(payload)


@dataclass
class RunContext:
    """Everything a stage needs: settings, the manifest, force flag, progress sink."""

    settings: Settings
    manifest: RunManifest
    force: bool = False
    progress: ProgressCallback | None = None

    def report(self, percent: int, message: str) -> None:
        if self.progress is not None:
            self.progress(percent, message)

    def scoped(self, start: int, end: int) -> RunContext:
        """A copy whose stage-local 0–100 progress maps onto [start, end] globally."""
        parent = self.progress

        def remap(percent: int, message: str) -> None:
            if parent is not None:
                parent(start + (end - start) * max(0, min(percent, 100)) // 100, message)

        return replace(self, progress=remap)


@dataclass
class StageOutcome:
    """What a stage produced: artifact paths + light metadata (+ cache-skip flag)."""

    stage: str
    artifacts: dict[str, Path]
    meta: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False


# --- artifact path conventions (shared with the CLI where stages overlap) --------


def _window(settings: Settings) -> tuple[int, int]:
    return settings.time.start, settings.time.end


def items_path(settings: Settings) -> Path:
    start, end = _window(settings)
    return settings.paths.raw / f"items_{start}_{end}.json"


def monthly_path(settings: Settings) -> Path:
    start, end = _window(settings)
    return settings.paths.interim / f"ndvi_monthly_{start}_{end}.zarr"


def _processed(settings: Settings, name: str, suffix: str) -> Path:
    start, end = _window(settings)
    return settings.paths.processed / f"{name}_{start}_{end}.{suffix}"


def _cached_outcome(ctx: RunContext, stage: str) -> StageOutcome | None:
    """Shared cache check: manifest hit + artifacts on disk + not forced."""
    if ctx.force:
        return None
    artifacts = ctx.manifest.fresh(stage)
    if artifacts is None:
        return None
    ctx.report(100, f"Stage '{stage}' is up to date — reusing cached outputs.")
    return StageOutcome(stage, artifacts, meta=ctx.manifest.meta(stage), skipped=True)


def _write_band(da: xr.DataArray, crs: object, path: Path, name: str) -> Path:
    """Write a single 2D DataArray to a GeoTIFF with an explicit CRS + band name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    band = da.rio.write_crs(crs)
    band.rio.to_raster(path)
    logger.info("Wrote %s -> %s", name, path)
    return path


def _open_band(path: Path) -> xr.DataArray:
    """Open a single-band GeoTIFF written by :func:`_write_band` as a 2D DataArray."""
    import rioxarray

    # open_rasterio is typed as a union (it can return lists for multi-subdataset
    # files); a single-band GeoTIFF is always one DataArray.
    da = cast("xr.DataArray", rioxarray.open_rasterio(path))
    return da.squeeze("band", drop=True)


# --- stages ----------------------------------------------------------------------


def stage_search(ctx: RunContext, backend: StacBackend | None = None) -> StageOutcome:
    """STAC search over the AOI; cache the (unsigned) scene list as JSON."""
    cached = _cached_outcome(ctx, STAGE_SEARCH)
    if cached is not None:
        return cached

    from vegevigie.catalog import (
        PlanetaryComputerBackend,
        build_search_params,
        search_and_cache,
    )

    settings = ctx.settings
    start, end = _window(settings)
    ctx.report(5, f"Searching Sentinel-2 scenes {start}–{end}…")
    params = build_search_params(
        bbox=settings.aoi.small_bbox,
        start_year=start,
        end_year=end,
        collection=settings.stac.collection,
        max_cloud_cover=settings.stac.max_cloud_cover,
    )
    path = items_path(settings)
    items = search_and_cache(backend or PlanetaryComputerBackend(), params, path, force=ctx.force)
    ctx.report(100, f"Found {len(items)} scenes.")
    meta = {"scene_count": len(items)}
    ctx.manifest.record(STAGE_SEARCH, {"items": path}, meta)
    return StageOutcome(STAGE_SEARCH, {"items": path}, meta)


def stage_composites(ctx: RunContext, backend: StacBackend | None = None) -> StageOutcome:
    """Datacube + SCL masking + NDVI + gap-aware monthly median composites (zarr)."""
    cached = _cached_outcome(ctx, STAGE_COMPOSITES)
    if cached is not None:
        return cached

    settings = ctx.settings
    src = items_path(settings)
    if not src.exists():
        msg = f"No cached scene list at {src} — run the '{STAGE_SEARCH}' stage first."
        raise StageInputError(msg)

    from vegevigie.catalog import PlanetaryComputerBackend, load_cached_items
    from vegevigie.composite import build_monthly_ndvi
    from vegevigie.datacube import build_cube
    from vegevigie.indices import masked_ndvi

    items = load_cached_items(src)
    if not items:
        msg = f"The cached scene list at {src} is empty — nothing to composite."
        raise StageInputError(msg)

    ctx.report(5, f"Building datacube from {len(items)} scenes at {settings.raster.resolution} m…")
    cube = build_cube(
        backend=backend or PlanetaryComputerBackend(),
        item_dicts=items,
        bbox=settings.aoi.small_bbox,
        resolution=settings.raster.resolution,
        chunk_size=settings.raster.chunk_size,
    )
    crs = cube.rio.crs

    ctx.report(40, "Cloud-masking + NDVI + monthly composites…")
    ndvi = masked_ndvi(cube["red"], cube["nir"], cube["scl"]).rename("ndvi")
    monthly = build_monthly_ndvi(ndvi, fill_max_gap=settings.composite.fill_max_gap).compute()
    if crs is not None:
        monthly = monthly.rio.write_crs(crs)

    out = monthly_path(settings)
    out.parent.mkdir(parents=True, exist_ok=True)
    monthly.to_dataset().to_zarr(out, mode="w")

    n_months = int(monthly.sizes.get("time", 0))
    ctx.report(100, f"Monthly composites written ({n_months} months).")
    meta = {"months": n_months, "scene_count": len(items)}
    ctx.manifest.record(STAGE_COMPOSITES, {"monthly": out}, meta)
    return StageOutcome(STAGE_COMPOSITES, {"monthly": out}, meta)


def stage_trend(ctx: RunContext) -> StageOutcome:
    """Per-pixel Mann-Kendall + Sen's slope → sen_slope / trend_class / p-value tifs."""
    cached = _cached_outcome(ctx, STAGE_TREND)
    if cached is not None:
        return cached

    settings = ctx.settings
    src = monthly_path(settings)
    if not src.exists():
        msg = f"No monthly composites at {src} — run the '{STAGE_COMPOSITES}' stage first."
        raise StageInputError(msg)

    from vegevigie.datacube import open_zarr
    from vegevigie.trend import trend_dataset

    monthly = open_zarr(src)["ndvi_monthly"]
    crs = monthly.rio.crs
    if crs is None:
        msg = f"The monthly composite store at {src} carries no CRS."
        raise RuntimeError(msg)

    n_months = int(monthly.sizes.get("time", 0))
    ctx.report(10, f"Per-pixel Mann-Kendall + Sen's slope over {n_months} months…")
    trend = trend_dataset(
        monthly, alpha=settings.trend.p_value, min_valid=settings.trend.min_valid_months
    ).compute()

    artifacts = {
        "sen_slope": _write_band(
            trend["sen_slope"], crs, _processed(settings, "trend_sen_slope", "tif"), "sen_slope"
        ),
        "trend_class": _write_band(
            trend["trend_class"], crs, _processed(settings, "trend_class", "tif"), "trend_class"
        ),
        "mk_pvalue": _write_band(
            trend["mk_pvalue"], crs, _processed(settings, "trend_pvalue", "tif"), "mk_pvalue"
        ),
    }
    classes = trend["trend_class"]
    meta = {
        "greening_pixels": int((classes == 1).sum()),
        "browning_pixels": int((classes == -1).sum()),
        "months": n_months,
    }
    ctx.report(100, "Trend rasters written.")
    ctx.manifest.record(STAGE_TREND, artifacts, meta)
    return StageOutcome(STAGE_TREND, artifacts, meta)


def stage_drought(ctx: RunContext) -> StageOutcome:
    """NDVI anomaly + VCI vs monthly climatology → rasters + AOI-mean timeline."""
    cached = _cached_outcome(ctx, STAGE_DROUGHT)
    if cached is not None:
        return cached

    settings = ctx.settings
    src = monthly_path(settings)
    if not src.exists():
        msg = f"No monthly composites at {src} — run the '{STAGE_COMPOSITES}' stage first."
        raise StageInputError(msg)

    from vegevigie.datacube import open_zarr
    from vegevigie.drought import drought_dataset, drought_timeline

    monthly = open_zarr(src)["ndvi_monthly"]
    crs = monthly.rio.crs
    if crs is None:
        msg = f"The monthly composite store at {src} carries no CRS."
        raise RuntimeError(msg)

    ctx.report(10, f"NDVI anomalies + VCI over {int(monthly.sizes.get('time', 0))} months…")
    drought = drought_dataset(monthly).compute()
    mean_anomaly = drought["ndvi_anomaly"].mean("time")
    min_vci = drought["vci"].min("time")
    timeline = drought_timeline(drought["ndvi_anomaly"]).compute()

    timeline_path = _processed(settings, "drought_timeline", "parquet")
    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    timeline.to_dataframe().reset_index().to_parquet(timeline_path)

    artifacts = {
        "anomaly": _write_band(
            mean_anomaly, crs, _processed(settings, "drought_anomaly", "tif"), "mean_anomaly"
        ),
        "min_vci": _write_band(
            min_vci, crs, _processed(settings, "drought_min_vci", "tif"), "min_vci"
        ),
        "timeline": timeline_path,
    }
    series = timeline.to_series()
    meta = {"driest_month": str(series.idxmin().date()) if len(series) else None}
    ctx.report(100, "Drought rasters + timeline written.")
    ctx.manifest.record(STAGE_DROUGHT, artifacts, meta)
    return StageOutcome(STAGE_DROUGHT, artifacts, meta)


def _zones_fingerprint(zones: gpd.GeoDataFrame) -> str:
    """Content hash of a zones layer, so the zonal cache notices a changed layer."""
    digest = hashlib.sha256()
    for wkb in zones.geometry.to_wkb():
        digest.update(wkb)
    return digest.hexdigest()[:16]


def stage_zonal(ctx: RunContext, zones: gpd.GeoDataFrame) -> StageOutcome:
    """Aggregate the trend/drought rasters to zones → GPKG + GeoParquet + DuckDB."""
    settings = ctx.settings
    zones_fp = _zones_fingerprint(zones)
    if not ctx.force:
        artifacts = ctx.manifest.fresh(STAGE_ZONAL)
        if artifacts is not None and ctx.manifest.meta(STAGE_ZONAL).get("zones") == zones_fp:
            ctx.report(100, f"Stage '{STAGE_ZONAL}' is up to date — reusing cached outputs.")
            return StageOutcome(
                STAGE_ZONAL, artifacts, meta=ctx.manifest.meta(STAGE_ZONAL), skipped=True
            )

    trend_arts = ctx.manifest.fresh(STAGE_TREND)
    if trend_arts is None:
        msg = f"No trend rasters recorded — run the '{STAGE_TREND}' stage first."
        raise StageInputError(msg)
    drought_arts = ctx.manifest.fresh(STAGE_DROUGHT) or {}

    from vegevigie.store import write_duckdb, write_geoparquet, write_gpkg
    from vegevigie.zonal import commune_stats

    ctx.report(10, f"Zonal aggregation over {len(zones)} zones…")
    stats = commune_stats(
        zones,
        sen_slope=_open_band(trend_arts["sen_slope"]),
        trend_class=_open_band(trend_arts["trend_class"]),
        mean_anomaly=_open_band(drought_arts["anomaly"]) if "anomaly" in drought_arts else None,
        min_vci=_open_band(drought_arts["min_vci"]) if "min_vci" in drought_arts else None,
    )

    artifacts = {
        "stats_parquet": write_geoparquet(stats, _processed(settings, "zonal_stats", "parquet")),
        "stats_gpkg": write_gpkg(stats, _processed(settings, "zonal_stats", "gpkg")),
        "duckdb": write_duckdb(
            stats.drop(columns="geometry"),
            settings.paths.processed / "vegevigie.duckdb",
            table="commune_stats",
        ),
    }
    meta = {"zones": zones_fp, "n_zones": len(zones)}
    ctx.report(100, "Zonal statistics written (GPKG + GeoParquet + DuckDB).")
    ctx.manifest.record(STAGE_ZONAL, artifacts, meta)
    return StageOutcome(STAGE_ZONAL, artifacts, meta)


def stage_rank(
    ctx: RunContext,
    metric: str = "mean_sen_slope",
    ascending: bool = False,
    limit: int = 10,
) -> StageOutcome:
    """Rank zones by a zonal metric (DuckDB query) → CSV + row preview in meta.

    Cheap and parameter-dependent, so never manifest-cached — it always re-queries.
    """
    settings = ctx.settings
    db_path = settings.paths.processed / "vegevigie.duckdb"
    if not db_path.exists():
        msg = f"No DuckDB store at {db_path} — run the '{STAGE_ZONAL}' stage first."
        raise StageInputError(msg)

    from vegevigie.store import rank_communes

    ctx.report(20, f"Ranking zones by {metric} ({'asc' if ascending else 'desc'}, top {limit})…")
    ranked = rank_communes(db_path, metric=metric, ascending=ascending, limit=limit)
    out = _processed(settings, f"rank_{metric}", "csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(out, index=False)

    name_col = "nom" if "nom" in ranked.columns else None
    rows = [
        [str(row[name_col]) if name_col else str(i), float(row[metric])]
        for i, (_, row) in enumerate(ranked.iterrows())
        if metric in ranked.columns
    ]
    ctx.report(100, f"Ranking written ({len(ranked)} rows).")
    return StageOutcome(STAGE_RANK, {"csv": out}, {"metric": metric, "rows": rows})


def run_stage(
    name: str,
    settings: Settings,
    *,
    zones: gpd.GeoDataFrame | None = None,
    force: bool = False,
    progress: ProgressCallback | None = None,
    backend: StacBackend | None = None,
    metric: str = "mean_sen_slope",
    ascending: bool = False,
    limit: int = 10,
) -> StageOutcome:
    """Run a single stage by name — the one entry point ``qgis_runner`` and the
    ScruTech per-stage algorithms share (in-process and external modes alike)."""
    manifest = RunManifest.for_settings(settings)
    ctx = RunContext(settings=settings, manifest=manifest, force=force, progress=progress)
    if name == STAGE_SEARCH:
        return stage_search(ctx, backend=backend)
    if name == STAGE_COMPOSITES:
        return stage_composites(ctx, backend=backend)
    if name == STAGE_TREND:
        return stage_trend(ctx)
    if name == STAGE_DROUGHT:
        return stage_drought(ctx)
    if name == STAGE_ZONAL:
        if zones is None:
            msg = "The zonal stage needs a zones layer."
            raise ValueError(msg)
        return stage_zonal(ctx, zones)
    if name == STAGE_RANK:
        return stage_rank(ctx, metric=metric, ascending=ascending, limit=limit)
    msg = f"Unknown stage {name!r} — expected one of {ALL_STAGES}."
    raise ValueError(msg)
