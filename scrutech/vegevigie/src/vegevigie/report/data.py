"""Discover which ScruTech pillar outputs live in a results folder — pure, testable.

Each pillar writes files with known names; the report shows only what it finds, so one
report page works whether the user ran one pillar or all five.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
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
        return any(v is not None for k, v in vars(self).items() if k != "folder")

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


def discover(results_dir: str | Path, aoi_id: str | None = None) -> ReportInputs:
    """Scan a results folder, or the central store for one AOI."""
    folder = Path(results_dir)
    files = (
        sorted(Path(path) for path in folder.glob(f"*/aoi={aoi_id}/output/*")) if aoi_id else None
    )

    def first(pattern: str) -> Path | None:
        hits = (
            [path for path in files if fnmatch(path.name, pattern)]
            if files is not None
            else list(folder.glob(pattern))
        )
        return sorted(hits)[0] if hits else None

    return ReportInputs(
        folder=folder,
        biotrame=first("biotrame_priority.geojson"),
        ecobuage_aptitude=first("ecobuage_aptitude.tif"),
        ecobuage_classes=first("ecobuage_classes.tif"),
        trend=first("trend_sen_slope_*.tif") or first("trend_*.tif"),
        drought=first("drought_anomaly_*.tif") or first("drought_*.tif"),
        interface_line=first("interface_line.geojson"),
        interface_zone=first("interface_zone.geojson"),
        alphaearth_change=first("alphaearth_change_*.geojson"),
        zonal=first("zonal_stats_*.parquet"),
    )
