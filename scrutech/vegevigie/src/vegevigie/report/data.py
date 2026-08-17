"""Discover which ScruTech pillar outputs live in a results folder — pure, testable.

Each pillar writes files with known names; the report shows only what it finds, so one
report page works whether the user ran one pillar or all five.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _first(folder: Path, pattern: str) -> Path | None:
    """The first file matching ``pattern`` in ``folder`` (sorted), or None."""
    hits = sorted(folder.glob(pattern))
    return hits[0] if hits else None


@dataclass(frozen=True)
class ReportInputs:
    """Paths to the pillar outputs found in a results folder (any may be None)."""

    folder: Path
    biotrame: Path | None = None
    ecobuage_aptitude: Path | None = None
    ecobuage_classes: Path | None = None
    trend: Path | None = None
    drought: Path | None = None
    interface_line: Path | None = None
    interface_zone: Path | None = None
    alphaearth_change: Path | None = None
    zonal: Path | None = None

    def any(self) -> bool:
        """True if at least one pillar output was found."""
        return any(
            v is not None
            for k, v in vars(self).items()
            if k != "folder"
        )

    def present(self) -> list[str]:
        """Names of the pillars whose outputs are present (for a summary line)."""
        mapping = {
            "Biotrame": self.biotrame,
            "Écobuage": self.ecobuage_classes or self.ecobuage_aptitude,
            "VegeVigie (tendance)": self.trend,
            "VegeVigie (sécheresse)": self.drought,
            "PAF (interface)": self.interface_line,
            "AlphaEarth (changement)": self.alphaearth_change,
        }
        return [name for name, path in mapping.items() if path is not None]


def discover(results_dir: str | Path) -> ReportInputs:
    """Scan ``results_dir`` for known pillar output files."""
    folder = Path(results_dir)
    return ReportInputs(
        folder=folder,
        biotrame=_first(folder, "biotrame_priority.geojson"),
        ecobuage_aptitude=_first(folder, "ecobuage_aptitude.tif"),
        ecobuage_classes=_first(folder, "ecobuage_classes.tif"),
        trend=_first(folder, "trend_sen_slope_*.tif") or _first(folder, "trend_*.tif"),
        drought=_first(folder, "drought_anomaly_*.tif") or _first(folder, "drought_*.tif"),
        interface_line=_first(folder, "interface_line.geojson"),
        interface_zone=_first(folder, "interface_zone.geojson"),
        alphaearth_change=_first(folder, "alphaearth_change_*.geojson"),
        zonal=_first(folder, "zonal_stats_*.parquet"),
    )
