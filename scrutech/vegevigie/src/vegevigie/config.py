"""Typed, YAML-backed configuration.

Everything tunable in the pipeline (AOI, date window, cloud threshold, resolution,
significance level) lives in ``config/default.yaml`` and is validated here with
pydantic models. Pipeline stages receive a :class:`Settings` object and never
read files or hard-code thresholds themselves (CLAUDE.md §7).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

def _find_default_config() -> Path:
    """``config/default.yaml`` sits two levels up in the ``src/`` layout and one level
    up in the bundled QGIS-plugin layout; probe both so this file works verbatim in each."""
    here = Path(__file__).resolve()
    for parent in (here.parents[2], here.parents[1]):
        candidate = parent / "config" / "default.yaml"
        if candidate.exists():
            return candidate
    return here.parents[2] / "config" / "default.yaml"


DEFAULT_CONFIG_PATH = _find_default_config()


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


class InterfaceConfig(BaseModel):
    """Wildland-Urban Interface (forest↔built-up frontier) parameters for the PAFF layer."""

    contact_m: float = Field(
        gt=0, description="Forest within this distance of a building counts as interface (metres)"
    )
    metric_crs: str = Field(description="Projected CRS for all distance/area maths (e.g. L93)")


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
    interface: InterfaceConfig
    paths: PathsConfig


def load_settings(path: Path | None = None) -> Settings:
    """Load and validate settings from a YAML file (default: ``config/default.yaml``)."""
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open() as fh:
        raw = yaml.safe_load(fh)
    return Settings.model_validate(raw)
