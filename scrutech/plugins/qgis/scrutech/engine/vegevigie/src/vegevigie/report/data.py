"""Discover which ScruTech pillar outputs live in a results folder — pure, testable.

Each pillar writes files with known names; the report shows only what it finds, so one
report page works whether the user ran one pillar or all five. When a product was computed
several times, the most recent file wins, and every VegeVigie layer comes from the same
period as the most recent trend.
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class ReportInputs:
    """Paths to the pillar outputs found in a results folder (any may be None)."""

    folder: Path
    trend: Path | None = None
    trend_class: Path | None = None
    drought: Path | None = None
    stress: Path | None = None
    zonal: Path | None = None
    ecobuage_aptitude: Path | None = None
    ecobuage_classes: Path | None = None
    interface_line: Path | None = None
    interface_zone: Path | None = None
    biotrame: Path | None = None
    alphaearth_change: Path | None = None
    projection: Path | None = None

    def any(self) -> bool:
        """True if at least one pillar output was found."""
        # vars(self) donne le dictionnaire {nom_du_champ: valeur} de l'instance — pratique
        # ici pour parcourir TOUS les champs sans les lister un par un à la main (sauf
        # "folder", qui n'est pas un résultat de pilier mais le dossier scanné).
        return any(v is not None for k, v in vars(self).items() if k != "folder")

    def present(self) -> list[str]:
        """Names of the pillars whose outputs are present (for a summary line)."""
        mapping = {
            "VegeVigie": self.trend or self.drought,
            "PAFF": self.interface_line,
            "Écobuage": self.ecobuage_classes or self.ecobuage_aptitude,
            "Biotrame": self.biotrame,
            "AlphaEarth": self.alphaearth_change,
            "Projection climatique": self.projection,
        }
        return [name for name, path in mapping.items() if path is not None]


def discover(results_dir: str | Path, aoi_id: str | None = None) -> ReportInputs:
    """Scan a results folder, or the central store for one AOI."""
    folder = Path(results_dir)
    files = list(folder.glob(f"*/aoi={aoi_id}/output/*")) if aoi_id else list(folder.glob("*"))

    def latest(pattern: str) -> Path | None:
        hits = [path for path in files if fnmatch(path.name, pattern)]
        return max(hits, key=lambda p: p.stat().st_mtime) if hits else None

    trend = latest("trend_sen_slope_*.tif")
    period = trend.stem.removeprefix("trend_sen_slope_") if trend else "*"
    return ReportInputs(
        folder=folder,
        trend=trend,
        trend_class=latest(f"trend_class_{period}.tif"),
        drought=latest(f"drought_anomaly_{period}.tif"),
        stress=latest(f"drought_frequency_{period}.tif"),
        zonal=latest(f"zonal_stats_{period}.parquet"),
        ecobuage_aptitude=latest("ecobuage_aptitude.tif"),
        ecobuage_classes=latest("ecobuage_classes.tif"),
        interface_line=latest("interface_line.geojson"),
        interface_zone=latest("interface_zone.geojson"),
        biotrame=latest("biotrame_priority.geojson"),
        alphaearth_change=latest("alphaearth_change_*[0-9].geojson"),
        projection=latest("projection_climat.json"),
    )
