"""ScruTech Processing provider — the algorithm registry shown in QGIS."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.analyze_extent import AnalyzeExtentAlgorithm
from .algorithms.ecobuage_aptitude import EcobuageAptitudeAlgorithm
from .algorithms.load_communes import LoadCommunesAlgorithm
from .algorithms.mini_dc_sites import MiniDcSitesAlgorithm
from .algorithms.paf_interface import InterfaceHabitatForetAlgorithm
from .algorithms.sdbpi_vacance import SdbpiVacanceAlgorithm


class ScruTechProvider(QgsProcessingProvider):
    """Groups the ScruTech algorithms under one Processing Toolbox entry."""

    def loadAlgorithms(self) -> None:  # noqa: N802 — QGIS API name
        self.addAlgorithm(AnalyzeExtentAlgorithm())
        self.addAlgorithm(LoadCommunesAlgorithm())
        self.addAlgorithm(InterfaceHabitatForetAlgorithm())
        self.addAlgorithm(EcobuageAptitudeAlgorithm())
        self.addAlgorithm(SdbpiVacanceAlgorithm())
        self.addAlgorithm(MiniDcSitesAlgorithm())

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
