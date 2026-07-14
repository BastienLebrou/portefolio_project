"""VegeVigie command-line interface.

One typer command per pipeline stage (CLAUDE.md §4). Every stage is idempotent,
reads its parameters from :mod:`vegevigie.config`, writes under ``data/`` and can
run standalone. M0 wires the commands; each milestone replaces one stub with the
real implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

import typer

from vegevigie import __version__
from vegevigie.config import Settings, load_settings

app = typer.Typer(
    name="vegevigie",
    help="VegeVigie — NDVI trends & drought stress from Sentinel-2, commune by commune.",
    no_args_is_help=True,
)

logger = logging.getLogger("vegevigie")

ConfigOpt = Annotated[
    Path | None,
    typer.Option("--config", help="Path to a YAML config file (default: config/default.yaml)."),
]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Enable debug logging.")]
ForceOpt = Annotated[bool, typer.Option("--force", help="Recompute even if cached output exists.")]
SmallOpt = Annotated[
    bool,
    typer.Option(
        "--small/--full",
        help="Restrict AOI to the smoke-test bbox (default) vs the whole département.",
    ),
]
StartOpt = Annotated[
    int | None, typer.Option("--start", help="Override start year (default: config time.start).")
]
EndOpt = Annotated[
    int | None, typer.Option("--end", help="Override end year (default: config time.end).")
]


def _setup(config: Path | None, verbose: bool) -> Settings:
    """Shared bootstrap for every stage: logging level + validated settings."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    settings = load_settings(config)
    logger.debug("Loaded settings: %s", settings.model_dump())
    return settings


def _not_implemented(stage: str, milestone: str) -> None:
    typer.echo(f"'{stage}' is not implemented yet — it lands in milestone {milestone}.")
    raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", help="Print the version and exit.")] = False,
) -> None:
    if version:
        typer.echo(f"vegevigie {__version__}")
        raise typer.Exit()


@app.command()
def aoi(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    small: SmallOpt = True,
) -> None:
    """Build the AOI GeoParquet from official admin boundaries (dept 07 by default)."""
    from vegevigie.aoi import build_aoi

    settings = _setup(config, verbose)
    small_bbox = settings.aoi.small_bbox if small else None
    communes_path, aoi_path = build_aoi(
        dept=settings.aoi.departement,
        name=settings.aoi.name,
        raw_dir=settings.paths.raw,
        small_bbox=small_bbox,
        force=force,
    )
    scope = "small bbox" if small else "full département"
    typer.echo(f"AOI built ({scope}): {aoi_path}")
    typer.echo(f"Communes layer: {communes_path}")


@app.command()
def search(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    small: SmallOpt = True,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """STAC search over the AOI; cache the Sentinel-2 item list in data/raw."""
    import geopandas as gpd

    from vegevigie.catalog import (
        PlanetaryComputerBackend,
        build_search_params,
        search_and_cache,
        summarize_item,
    )

    settings = _setup(config, verbose)
    aoi_path = settings.paths.raw / "aoi.parquet"
    if not aoi_path.exists():
        typer.echo(f"AOI not found at {aoi_path} — run `vegevigie aoi` first.")
        raise typer.Exit(code=1)

    # (minx, miny, maxx, maxy) in WGS84 — as plain floats: numpy scalars from
    # total_bounds are not JSON-serializable when the search params get cached.
    bbox = tuple(float(c) for c in gpd.read_parquet(aoi_path).total_bounds)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    params = build_search_params(
        bbox=bbox,  # type: ignore[arg-type]
        start_year=start_year,
        end_year=end_year,
        collection=settings.stac.collection,
        max_cloud_cover=settings.stac.max_cloud_cover,
    )
    cache_path = settings.paths.raw / f"items_{start_year}_{end_year}.json"
    typer.echo(
        f"Searching {settings.stac.collection} over bbox {tuple(round(c, 3) for c in bbox)} "
        f"for {start_year}-{end_year} (cloud < {settings.stac.max_cloud_cover}%)..."
    )
    try:
        items = search_and_cache(PlanetaryComputerBackend(), params, cache_path, force=force)
    except Exception as exc:  # noqa: BLE001 — surface any network/STAC failure clearly
        logger.debug("STAC search failed", exc_info=True)
        typer.echo(f"STAC search failed: {exc}")
        typer.echo(
            "If this is a proxy 403/407, the egress policy is blocking "
            "planetarycomputer.microsoft.com — allowlist it (or run outside the "
            "restricted network) and retry. The AOI and cached results are unaffected."
        )
        raise typer.Exit(code=1) from exc

    typer.echo(f"Found {len(items)} scenes; cached to {cache_path}")
    for summary in (summarize_item(it) for it in items[:5]):
        typer.echo(f"  {summary['datetime']}  cloud={summary['cloud_cover']}  {summary['tile']}")


def _network_hint(exc: Exception) -> None:
    """Shared blocked-host guidance for the network-bound datacube stages."""
    logger.debug("network stage failed", exc_info=True)
    typer.echo(f"Failed: {exc}")
    typer.echo(
        "If this is a proxy 403/407, the egress policy is blocking "
        "planetarycomputer.microsoft.com — allowlist it (or run outside the "
        "restricted network) and retry."
    )
    raise typer.Exit(code=1) from exc


@app.command()
def cube(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """Build the lazy xarray datacube (Red, NIR, SCL) and cache it as .zarr."""
    import geopandas as gpd

    from vegevigie.catalog import PlanetaryComputerBackend, load_cached_items
    from vegevigie.datacube import build_cube, write_zarr

    settings = _setup(config, verbose)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    items_path = settings.paths.raw / f"items_{start_year}_{end_year}.json"
    aoi_path = settings.paths.raw / "aoi.parquet"
    if not items_path.exists() or not aoi_path.exists():
        typer.echo(f"Missing {items_path} or {aoi_path} — run `vegevigie aoi` and `search` first.")
        raise typer.Exit(code=1)

    bbox = tuple(float(c) for c in gpd.read_parquet(aoi_path).total_bounds)
    items = load_cached_items(items_path)
    zarr_path = settings.paths.interim / f"cube_{start_year}_{end_year}.zarr"

    typer.echo(f"Building datacube from {len(items)} items at {settings.raster.resolution}m...")
    try:
        cube_ds = build_cube(
            backend=PlanetaryComputerBackend(),
            item_dicts=items,
            bbox=bbox,  # type: ignore[arg-type]
            resolution=settings.raster.resolution,
            chunk_size=settings.raster.chunk_size,
        )
        write_zarr(cube_ds, zarr_path, force=force)
    except Exception as exc:  # noqa: BLE001
        _network_hint(exc)

    typer.echo(f"Datacube cached: {zarr_path}")


@app.command()
def ndvi(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """SCL cloud-mask + NDVI per scene, then gap-aware monthly median composites."""
    from vegevigie.composite import build_monthly_ndvi
    from vegevigie.datacube import open_zarr
    from vegevigie.indices import masked_ndvi

    settings = _setup(config, verbose)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    cube_path = settings.paths.interim / f"cube_{start_year}_{end_year}.zarr"
    if not cube_path.exists():
        typer.echo(f"Datacube not found at {cube_path} — run `vegevigie cube` first.")
        raise typer.Exit(code=1)

    cube_ds = open_zarr(cube_path)
    ndvi_da = masked_ndvi(cube_ds["red"], cube_ds["nir"], cube_ds["scl"]).rename("ndvi")
    monthly = build_monthly_ndvi(ndvi_da, fill_max_gap=settings.composite.fill_max_gap)

    ndvi_path = settings.paths.interim / f"ndvi_{start_year}_{end_year}.zarr"
    monthly_path = settings.paths.interim / f"ndvi_monthly_{start_year}_{end_year}.zarr"
    if monthly_path.exists() and not force:
        typer.echo(f"Monthly NDVI already cached at {monthly_path} (use --force to rebuild).")
        raise typer.Exit(code=0)

    mode: Literal["w", "w-"] = "w" if force else "w-"
    ndvi_da.to_dataset().to_zarr(ndvi_path, mode=mode)
    monthly.to_dataset().to_zarr(monthly_path, mode=mode)
    typer.echo(f"Masked NDVI cached: {ndvi_path}")
    typer.echo(
        f"Monthly composites cached: {monthly_path} "
        f"({monthly.sizes.get('time', 0)} months, gap-fill={settings.composite.fill_max_gap})"
    )


@app.command()
def trend(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """Per-pixel Mann-Kendall + Sen's slope -> greening/browning trend raster."""
    from vegevigie.datacube import open_zarr
    from vegevigie.trend import trend_dataset

    settings = _setup(config, verbose)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    monthly_path = settings.paths.interim / f"ndvi_monthly_{start_year}_{end_year}.zarr"
    if not monthly_path.exists():
        typer.echo(f"Monthly NDVI not found at {monthly_path} — run `vegevigie ndvi` first.")
        raise typer.Exit(code=1)

    out_path = settings.paths.processed / f"trend_{start_year}_{end_year}.zarr"
    if out_path.exists() and not force:
        typer.echo(f"Trend raster already cached at {out_path} (use --force to rebuild).")
        raise typer.Exit(code=0)

    monthly = open_zarr(monthly_path)["ndvi_monthly"]
    typer.echo(
        f"Running per-pixel Mann-Kendall + Sen's slope over {monthly.sizes['time']} months..."
    )
    result = trend_dataset(
        monthly,
        alpha=settings.trend.p_value,
        min_valid=settings.trend.min_valid_months,
    ).compute()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_zarr(out_path, mode="w")

    classes = result["trend_class"]
    n_green = int((classes == 1).sum())
    n_brown = int((classes == -1).sum())
    typer.echo(f"Trend raster cached: {out_path}")
    typer.echo(
        f"  greening pixels: {n_green} | browning pixels: {n_brown} (p<{settings.trend.p_value})"
    )


@app.command()
def drought(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """NDVI anomalies / VCI vs monthly climatology -> drought raster + timeline."""
    from vegevigie.datacube import open_zarr
    from vegevigie.drought import drought_dataset, drought_timeline

    settings = _setup(config, verbose)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    monthly_path = settings.paths.interim / f"ndvi_monthly_{start_year}_{end_year}.zarr"
    if not monthly_path.exists():
        typer.echo(f"Monthly NDVI not found at {monthly_path} — run `vegevigie ndvi` first.")
        raise typer.Exit(code=1)

    raster_path = settings.paths.processed / f"drought_{start_year}_{end_year}.zarr"
    timeline_path = settings.paths.processed / f"drought_timeline_{start_year}_{end_year}.parquet"
    if raster_path.exists() and not force:
        typer.echo(f"Drought raster already cached at {raster_path} (use --force to rebuild).")
        raise typer.Exit(code=0)

    monthly = open_zarr(monthly_path)["ndvi_monthly"]
    typer.echo(f"Computing NDVI anomalies + VCI over {monthly.sizes['time']} months...")
    ds = drought_dataset(monthly).compute()
    timeline = drought_timeline(ds["ndvi_anomaly"]).compute()

    raster_path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_zarr(raster_path, mode="w")
    timeline.to_dataframe().reset_index().to_parquet(timeline_path)

    driest = timeline.to_series().idxmin()
    typer.echo(f"Drought raster cached: {raster_path}")
    typer.echo(f"Drought timeline cached: {timeline_path}")
    typer.echo(f"  driest month (lowest AOI-mean anomaly): {driest.date()}")


@app.command()
def zonal(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """Aggregate trend/drought rasters to communes -> DuckDB + GeoParquet."""
    import geopandas as gpd

    from vegevigie.datacube import open_zarr
    from vegevigie.store import rank_communes, write_duckdb, write_geoparquet
    from vegevigie.zonal import commune_stats

    settings = _setup(config, verbose)
    start_year = start or settings.time.start
    end_year = end or settings.time.end

    trend_path = settings.paths.processed / f"trend_{start_year}_{end_year}.zarr"
    drought_path = settings.paths.processed / f"drought_{start_year}_{end_year}.zarr"
    communes_path = settings.paths.raw / f"communes_{settings.aoi.departement}.parquet"
    for required in (trend_path, communes_path):
        if not required.exists():
            typer.echo(f"Missing {required} — run the earlier stages first.")
            raise typer.Exit(code=1)

    # Same name the pipeline and the dashboard use (zonal_stats_*), so `vegevigie zonal`
    # outputs are discoverable by find_outputs. (B1: was commune_stats_*, invisible.)
    out_parquet = settings.paths.processed / f"zonal_stats_{start_year}_{end_year}.parquet"
    duckdb_path = settings.paths.processed / "vegevigie.duckdb"
    if out_parquet.exists() and not force:
        typer.echo(f"Commune stats already cached at {out_parquet} (use --force to rebuild).")
        raise typer.Exit(code=0)

    communes = gpd.read_parquet(communes_path)
    trend = open_zarr(trend_path)
    mean_anomaly = min_vci = None
    if drought_path.exists():
        drought = open_zarr(drought_path)
        mean_anomaly = drought["ndvi_anomaly"].mean("time")
        min_vci = drought["vci"].min("time")

    typer.echo(f"Aggregating trend/drought rasters to {len(communes)} communes...")
    stats = commune_stats(
        communes,
        sen_slope=trend["sen_slope"],
        trend_class=trend["trend_class"],
        mean_anomaly=mean_anomaly,
        min_vci=min_vci,
    )
    write_geoparquet(stats, out_parquet)
    write_duckdb(stats.drop(columns="geometry"), duckdb_path, table="commune_stats")

    typer.echo(f"Commune stats cached: {out_parquet}")
    typer.echo(f"DuckDB: {duckdb_path} (table commune_stats)")
    top = rank_communes(duckdb_path, metric="mean_sen_slope", ascending=False, limit=5)
    typer.echo("Top greening communes (mean Sen slope):")
    for _, row in top.iterrows():
        typer.echo(f"  {row['nom']:<28} slope={row['mean_sen_slope']:+.5f}")


@app.command()
def interface(
    forest: Annotated[Path, typer.Argument(help="Forest zones layer (parquet/gpkg/shp/geojson).")],
    bati: Annotated[Path, typer.Argument(help="Built-up zones layer (parquet/gpkg/shp/geojson).")],
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    aoi: Annotated[
        Path | None,
        typer.Option("--aoi", help="AOI layer (any CRS) to clip to; else the whole extent."),
    ] = None,
    bbox: Annotated[
        str | None,
        typer.Option("--bbox", help="Emprise 'minx,miny,maxx,maxy' in the config metric CRS."),
    ] = None,
    contact_m: Annotated[
        float | None,
        typer.Option("--contact-m", help="Override interface distance (m; default: config)."),
    ] = None,
) -> None:
    """Forest/built-up interface (WUI) for the PAFF layer: frontier line + contact band."""
    from vegevigie.interface import build_interface

    settings = _setup(config, verbose)
    for required in (forest, bati):
        if not required.exists():
            typer.echo(f"Input layer not found: {required}")
            raise typer.Exit(code=1)

    box_coords: tuple[float, float, float, float] | None = None
    if bbox is not None:
        parts = tuple(float(v) for v in bbox.split(","))
        if len(parts) != 4:
            typer.echo("--bbox must be 'minx,miny,maxx,maxy' (4 comma-separated numbers).")
            raise typer.Exit(code=1)
        box_coords = parts  # type: ignore[assignment]

    line_path, zone_path, metrics = build_interface(
        forest_path=forest,
        bati_path=bati,
        out_dir=settings.paths.processed,
        metric_crs=settings.interface.metric_crs,
        contact_m=contact_m if contact_m is not None else settings.interface.contact_m,
        aoi_path=aoi,
        bbox=box_coords,
        force=force,
    )
    typer.echo(f"Interface line: {line_path}")
    typer.echo(f"Interface zone: {zone_path}")
    if metrics:
        typer.echo(
            f"  frontier: {metrics['interface_length_m'] / 1000:.2f} km | "
            f"band to treat: {metrics['interface_zone_ha']:.1f} ha "
            f"(contact {metrics['contact_m']:.0f} m)"
        )


@app.command()
def dashboard(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Launch the Streamlit + leafmap dashboard on the pipeline's commune outputs."""
    import os
    import subprocess
    import sys

    settings = _setup(config, verbose)
    app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
    # Pass the resolved output dir so the app finds data/ regardless of Streamlit's CWD.
    env = os.environ | {"VEGEVIGIE_DATA_DIR": str(settings.paths.processed.resolve())}
    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path)], env=env, check=False
        )
    except FileNotFoundError:
        typer.echo(
            "Streamlit is not installed — run `uv sync` (or `pip install streamlit leafmap`)."
        )
        raise typer.Exit(code=1) from None


@app.command()
def run(
    config: ConfigOpt = None,
    verbose: VerboseOpt = False,
    force: ForceOpt = False,
    small: SmallOpt = True,
    start: StartOpt = None,
    end: EndOpt = None,
) -> None:
    """Run the full pipeline end-to-end (small-AOI smoke run by default).

    Chains aoi -> search -> cube -> ndvi -> trend -> drought -> zonal, reusing each
    stage's caching. Stops with a clear message if a stage fails (e.g. the STAC host
    is blocked by an egress policy). The dashboard is launched separately (M7).
    """
    steps: list[tuple[str, Callable[[], None]]] = [
        ("aoi", lambda: aoi(config, verbose, force, small)),
        ("search", lambda: search(config, verbose, force, small, start, end)),
        ("cube", lambda: cube(config, verbose, force, start, end)),
        ("ndvi", lambda: ndvi(config, verbose, force, start, end)),
        ("trend", lambda: trend(config, verbose, force, start, end)),
        ("drought", lambda: drought(config, verbose, force, start, end)),
        ("zonal", lambda: zonal(config, verbose, force, start, end)),
    ]
    for name, step in steps:
        typer.echo(f"── vegevigie {name} ──")
        try:
            step()
        except typer.Exit as exc:
            if exc.exit_code:  # non-zero -> a real failure; stop the pipeline
                typer.echo(f"Pipeline stopped at '{name}' (exit {exc.exit_code}).")
                raise
            # exit code 0 = stage skipped via cache / already done -> keep going
    typer.echo("Pipeline complete.")
