"""VegeVigie command-line interface.

One typer command per pipeline stage (CLAUDE.md §4). Every stage is idempotent,
reads its parameters from :mod:`vegevigie.config`, writes under ``data/`` and can
run standalone. M0 wires the commands; each milestone replaces one stub with the
real implementation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

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

    bbox = tuple(gpd.read_parquet(aoi_path).total_bounds)  # (minx, miny, maxx, maxy) in WGS84
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


@app.command()
def cube(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """Build the lazy xarray datacube (Red, NIR, SCL) and cache it as .zarr."""
    _setup(config, verbose)
    _not_implemented("cube", "M2")


@app.command()
def ndvi(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """SCL cloud-mask, compute NDVI and build monthly median composites."""
    _setup(config, verbose)
    _not_implemented("ndvi", "M2/M3")


@app.command()
def trend(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """Per-pixel Mann-Kendall + Sen's slope -> greening/browning trend raster."""
    _setup(config, verbose)
    _not_implemented("trend", "M4")


@app.command()
def drought(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """NDVI anomalies / VCI vs monthly climatology -> drought raster + timeline."""
    _setup(config, verbose)
    _not_implemented("drought", "M5")


@app.command()
def zonal(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """Aggregate trend/drought rasters to communes -> DuckDB + GeoParquet."""
    _setup(config, verbose)
    _not_implemented("zonal", "M6")


@app.command()
def dashboard(config: ConfigOpt = None, verbose: VerboseOpt = False) -> None:
    """Launch the Streamlit + leafmap dashboard."""
    _setup(config, verbose)
    _not_implemented("dashboard", "M7")


@app.command()
def run(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """Run the full pipeline end-to-end (small-AOI smoke run by default)."""
    _setup(config, verbose)
    _not_implemented("run", "M8")
