"""UI-free dashboard helpers: locate pipeline outputs, colour a trend value.

No ``streamlit`` / ``leafmap`` import here so this is importable and testable on
its own (the rendering lives in :mod:`vegevigie.dashboard.app`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.colors as mcolors
from matplotlib import colormaps

# Diverging colour for Sen's slope (NDVI/month): red = browning, green = greening.
# ±0.02 NDVI/month spans the usual range at department scale; values are clamped.
_SLOPE_LIMIT = 0.02
_CMAP = colormaps["RdYlGn"]
NO_DATA_COLOR = "#cccccc"


def slope_color(value: float | None) -> str:
    """Hex colour for a mean Sen's-slope value (None/NaN -> neutral grey)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return NO_DATA_COLOR
    clamped = max(-_SLOPE_LIMIT, min(_SLOPE_LIMIT, value))
    unit = (clamped + _SLOPE_LIMIT) / (2 * _SLOPE_LIMIT)  # -> [0, 1]
    return mcolors.to_hex(_CMAP(unit))


@dataclass(frozen=True)
class Outputs:
    """Discovered pipeline output paths (any may be None if not produced yet)."""

    zonal: Path | None
    duckdb: Path | None
    timeline: Path | None

    def ready(self) -> bool:
        """True once the commune layer exists — the minimum to render anything."""
        return self.zonal is not None


def find_outputs(processed: Path) -> Outputs:
    """Locate the latest zonal-stats, DuckDB and drought-timeline outputs.

    Matches both the pipeline's ``*_<start>_<end>`` names and the demo's
    ``*_demo`` names; picks the lexically last when several windows are present.
    """

    def latest(pattern: str) -> Path | None:
        hits = sorted(processed.glob(pattern))
        return hits[-1] if hits else None

    db = processed / "vegevigie.duckdb"
    return Outputs(
        zonal=latest("zonal_stats_*.parquet"),
        duckdb=db if db.exists() else None,
        timeline=latest("drought_timeline_*.parquet"),
    )
