"""ScruTech Processing provider — the algorithm registry shown in QGIS."""

from __future__ import annotations

from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon

from .algorithms.alphaearth_change import AlphaEarthChangeAlgorithm
from .algorithms.analyze_extent import AnalyzeExtentAlgorithm
from .algorithms.biotrame_priority import BiotramePriorityAlgorithm
from .algorithms.diagnostic_complet import DiagnosticCompletAlgorithm
from .algorithms.ecobuage_aptitude import EcobuageAptitudeAlgorithm
from .algorithms.ecobuage_aptitude_aoi import EcobuageAptitudeFromAoiAlgorithm
from .algorithms.geoai_segment import GeoaiSegmentAlgorithm
from .algorithms.load_cached import LoadCachedAlgorithm
from .algorithms.load_communes import LoadCommunesAlgorithm
from .algorithms.mnt_aoi import MntFromAoiAlgorithm
from .algorithms.ortho_aoi import OrthoFromAoiAlgorithm
from .algorithms.paf_interface import InterfaceHabitatForetAlgorithm
from .algorithms.paf_interface_aoi import InterfaceFromAoiAlgorithm
from .algorithms.projection_aoi import ProjectionFromAoiAlgorithm
from .algorithms.report_launch import ReportLaunchAlgorithm
from .algorithms.setup_check import SetupCheckAlgorithm


# Un QgsProcessingProvider est le "dossier" qui regroupe une famille d'algorithmes dans
# la boîte à outils Processing de QGIS (comme "GDAL" ou "GRASS" y sont déjà des
# dossiers) ; `id()`/`name()`/`longName()`/`icon()` ci-dessous ne sont que l'identité
# affichée par QGIS, `loadAlgorithms()` est la seule méthode où se passe vraiment
# quelque chose : enregistrer chaque algorithme du plugin.
class ScruTechProvider(QgsProcessingProvider):
    """Groups the ScruTech algorithms under one Processing Toolbox entry."""

    def loadAlgorithms(self) -> None:  # noqa: N802 — QGIS API name
        # Ordered as the workflow reads in the toolbox (groups are numbered 0→6).
        # No group: the full diagnostic sits above the numbered groups.
        self.addAlgorithm(DiagnosticCompletAlgorithm())
        # 0 · Démarrer ici
        self.addAlgorithm(SetupCheckAlgorithm())
        # 1 · Préparer l'emprise
        self.addAlgorithm(LoadCommunesAlgorithm())
        self.addAlgorithm(MntFromAoiAlgorithm())
        self.addAlgorithm(OrthoFromAoiAlgorithm())
        # 2 · Analyser une emprise (dans l'ordre ①→④)
        self.addAlgorithm(AnalyzeExtentAlgorithm())
        self.addAlgorithm(AlphaEarthChangeAlgorithm())
        self.addAlgorithm(InterfaceFromAoiAlgorithm())
        self.addAlgorithm(EcobuageAptitudeFromAoiAlgorithm())
        # 3 · Croiser et prioriser
        self.addAlgorithm(BiotramePriorityAlgorithm())
        self.addAlgorithm(ProjectionFromAoiAlgorithm())
        # 4 · Consulter les résultats
        self.addAlgorithm(ReportLaunchAlgorithm())
        self.addAlgorithm(LoadCachedAlgorithm())
        # ponytail: SDBPi and mini data centers are hidden (off-topic for the plugin). Their
        # algorithm files stay in algorithms/; re-add them here and in package.py to ship again.
        # 5 · Outils avancés (couches en entrée)
        self.addAlgorithm(InterfaceHabitatForetAlgorithm())
        self.addAlgorithm(EcobuageAptitudeAlgorithm())
        # 6 · GeoAI (expérimental)
        self.addAlgorithm(GeoaiSegmentAlgorithm())

    def id(self) -> str:
        return "scrutech"

    def name(self) -> str:
        return "ScruTech"

    def longName(self) -> str:  # noqa: N802 — QGIS API name
        return "ScruTech : VegeVigie, AlphaEarth, PAFF, écobuage, Biotrame, GeoAI"

    def icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parent / "icon.svg"
        return QIcon(str(icon_path)) if icon_path.exists() else QgsProcessingProvider.icon(self)
