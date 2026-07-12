"""ScruTech Processing provider — the algorithm registry shown in QGIS."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.analyze_extent import AnalyzeExtentAlgorithm
from .algorithms.build_composites import BuildCompositesAlgorithm
from .algorithms.compute_drought import ComputeDroughtAlgorithm
from .algorithms.compute_trend import ComputeTrendAlgorithm
from .algorithms.load_communes import LoadCommunesAlgorithm
from .algorithms.rank_zones import RankZonesAlgorithm
from .algorithms.search_scenes import SearchScenesAlgorithm
from .algorithms.zonal_stats import ZonalStatsAlgorithm


class ScruTechProvider(QgsProcessingProvider):
    """Groups the ScruTech algorithms under one Processing Toolbox entry."""

    def loadAlgorithms(self) -> None:  # noqa: N802 — QGIS API name
        # One-click front door + the same pipeline exposed stage by stage, so the
        # stages can be chained in the Model Designer or run/forced individually.
        self.addAlgorithm(AnalyzeExtentAlgorithm())
        self.addAlgorithm(SearchScenesAlgorithm())
        self.addAlgorithm(BuildCompositesAlgorithm())
        self.addAlgorithm(ComputeTrendAlgorithm())
        self.addAlgorithm(ComputeDroughtAlgorithm())
        self.addAlgorithm(ZonalStatsAlgorithm())
        self.addAlgorithm(RankZonesAlgorithm())
        self.addAlgorithm(LoadCommunesAlgorithm())

    def id(self) -> str:
        return "scrutech"

    def name(self) -> str:
        return "ScruTech"

    def longName(self) -> str:  # noqa: N802 — QGIS API name
        return "ScruTech — vegetation trend & drought (VegeVigie)"

    def icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parent / "icon.svg"
        return QIcon(str(icon_path)) if icon_path.exists() else QgsProcessingProvider.icon(self)
