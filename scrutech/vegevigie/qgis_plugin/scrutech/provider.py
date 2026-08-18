"""ScruTech Processing provider — the algorithm registry shown in QGIS."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.alphaearth_change import AlphaEarthChangeAlgorithm
from .algorithms.analyze_extent import AnalyzeExtentAlgorithm
from .algorithms.biotrame_priority import BiotramePriorityAlgorithm
from .algorithms.ecobuage_aptitude import EcobuageAptitudeAlgorithm
from .algorithms.ecobuage_aptitude_aoi import EcobuageAptitudeFromAoiAlgorithm
from .algorithms.load_cached import LoadCachedAlgorithm
from .algorithms.load_communes import LoadCommunesAlgorithm
from .algorithms.mini_dc_sites import MiniDcSitesAlgorithm
from .algorithms.paf_interface import InterfaceHabitatForetAlgorithm
from .algorithms.paf_interface_aoi import InterfaceFromAoiAlgorithm
from .algorithms.report_launch import ReportLaunchAlgorithm
from .algorithms.sdbpi_vacance import SdbpiVacanceAlgorithm


class ScruTechProvider(QgsProcessingProvider):
    """Groups the ScruTech algorithms under one Processing Toolbox entry."""

    def loadAlgorithms(self) -> None:  # noqa: N802 — QGIS API name
        # Ordered as the workflow reads in the toolbox (groups are numbered 1→6).
        # 1 · Préparer l'emprise
        self.addAlgorithm(LoadCommunesAlgorithm())
        # 2 · Indicateurs par emprise (les piliers AOI-only, dans l'ordre ①→④)
        self.addAlgorithm(AnalyzeExtentAlgorithm())
        self.addAlgorithm(AlphaEarthChangeAlgorithm())
        self.addAlgorithm(InterfaceFromAoiAlgorithm())
        self.addAlgorithm(EcobuageAptitudeFromAoiAlgorithm())
        # 3 · Croiser & prioriser
        self.addAlgorithm(BiotramePriorityAlgorithm())
        # 4 · Restituer
        self.addAlgorithm(ReportLaunchAlgorithm())
        self.addAlgorithm(LoadCachedAlgorithm())
        # 5 · Bâti & territoire
        self.addAlgorithm(SdbpiVacanceAlgorithm())
        self.addAlgorithm(MiniDcSitesAlgorithm())
        # 6 · Outils avancés (couches en entrée)
        self.addAlgorithm(InterfaceHabitatForetAlgorithm())
        self.addAlgorithm(EcobuageAptitudeAlgorithm())

    def id(self) -> str:
        return "scrutech"

    def name(self) -> str:
        return "ScruTech"

    def longName(self) -> str:  # noqa: N802 — QGIS API name
        return (
            "ScruTech — geodata hub: VegeVigie, PAF fire interface, écobuage, "
            "SDBPi vacant buildings, mini data centers"
        )

    def icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parent / "icon.svg"
        return QIcon(str(icon_path)) if icon_path.exists() else QgsProcessingProvider.icon(self)
