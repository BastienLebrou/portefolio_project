"""Typed, YAML-backed configuration.

Everything tunable in the pipeline (AOI, date window, cloud threshold, resolution,
significance level) lives in ``config/default.yaml`` and is validated here with
pydantic models. Pipeline stages receive a :class:`Settings` object and never
read files or hard-code thresholds themselves (CLAUDE.md §7).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_HERE = Path(__file__).resolve()

# Environment override — an escape hatch when none of the layouts below apply
# (e.g. a site-specific config on a server, or debugging an install).
CONFIG_ENV_VAR = "VEGEVIGIE_CONFIG"

# The same engine runs from three different layouts, and the default config sits
# in a different place in each. Rather than assume one, try them in order:
#
# 1. dev / editable install — ``<repo>/src/vegevigie/config.py`` next to
#    ``<repo>/config/default.yaml``;
# 2. bundled inside the ScruTech QGIS plugin — ``scrutech/vegevigie/config.py``
#    with the config copied to ``scrutech/config/default.yaml`` by package.py;
# 3. pip-installed wheel — no repo around it, so the build force-includes a copy
#    inside the package itself (see pyproject.toml).
CONFIG_CANDIDATES: tuple[Path, ...] = (
    _HERE.parents[2] / "config" / "default.yaml",
    _HERE.parents[1] / "config" / "default.yaml",
    _HERE.parent / "default_config.yaml",
)


def default_config_path() -> Path:
    """Return the first default config that exists, or raise with where we looked."""
    env_value = os.environ.get(CONFIG_ENV_VAR)
    if env_value:
        candidate = Path(env_value)
        if not candidate.is_file():
            msg = f"{CONFIG_ENV_VAR} points at {candidate}, which is not a file."
            raise FileNotFoundError(msg)
        return candidate
    for candidate in CONFIG_CANDIDATES:
        if candidate.is_file():
            return candidate
    looked = "\n  ".join(str(c) for c in CONFIG_CANDIDATES)
    msg = (
        "Could not find VegeVigie's default configuration. Looked in:\n  "
        f"{looked}\n\nPass an explicit config path, or set the "
        f"{CONFIG_ENV_VAR} environment variable to a default.yaml."
    )
    raise FileNotFoundError(msg)


class AoiConfig(BaseModel):
    """Area of interest: a French département plus a small smoke-test bbox."""

    name: str
    departement: str
    small_bbox: tuple[float, float, float, float] = Field(
        description="WGS84 (min_lon, min_lat, max_lon, max_lat) bbox for smoke runs"
    )


class TimeConfig(BaseModel):
    """Analysis window in whole years, inclusive on both ends."""

    start: int = Field(ge=2015, description="Sentinel-2 has no usable data before 2015")
    end: int

    def model_post_init(self, __context: object) -> None:
        if self.end < self.start:
            msg = f"time.end ({self.end}) must be >= time.start ({self.start})"
            raise ValueError(msg)


class StacConfig(BaseModel):
    """STAC data-source parameters (Microsoft Planetary Computer by default)."""

    provider: str
    collection: str
    max_cloud_cover: float = Field(ge=0, le=100)


class RasterConfig(BaseModel):
    """Datacube geometry: working resolution and dask chunking."""

    resolution: int = Field(gt=0, description="Working resolution in metres")
    chunk_size: int = Field(gt=0, description="Dask chunk edge size in pixels")


class CompositeConfig(BaseModel):
    """Monthly-composite parameters."""

    fill_max_gap: int = Field(ge=0, description="Max consecutive months to gap-fill; 0 disables")


class TrendConfig(BaseModel):
    """Per-pixel trend-test parameters."""

    p_value: float = Field(gt=0, lt=1)
    min_valid_months: int = Field(ge=4, description="Min valid months to attempt a trend")


class PathsConfig(BaseModel):
    """Filesystem layout for pipeline outputs (all gitignored)."""

    data_dir: Path

    @property
    def raw(self) -> Path:
        return self.data_dir / "raw"

    @property
    def interim(self) -> Path:
        return self.data_dir / "interim"

    @property
    def processed(self) -> Path:
        return self.data_dir / "processed"


class Settings(BaseModel):
    """Root configuration object handed to every pipeline stage."""

    aoi: AoiConfig
    time: TimeConfig
    stac: StacConfig
    raster: RasterConfig
    composite: CompositeConfig
    trend: TrendConfig
    paths: PathsConfig


def load_settings(path: Path | None = None) -> Settings:
    """Load and validate settings from a YAML file.

    With no ``path``, the default config is resolved through
    :func:`default_config_path`, which handles the dev repo, the bundled QGIS
    plugin and a pip-installed wheel alike.
    """
    config_path = path or default_config_path()
    with config_path.open() as fh:
        raw = yaml.safe_load(fh)
    return Settings.model_validate(raw)
