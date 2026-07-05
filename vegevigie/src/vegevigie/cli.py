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
def aoi(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """Build the AOI GeoParquet from official admin boundaries (dept 07 by default)."""
    _setup(config, verbose)
    _not_implemented("aoi", "M1")


@app.command()
def search(config: ConfigOpt = None, verbose: VerboseOpt = False, force: ForceOpt = False) -> None:
    """STAC search over the AOI; cache the signed Sentinel-2 item list in data/raw."""
    _setup(config, verbose)
    _not_implemented("search", "M1")


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
