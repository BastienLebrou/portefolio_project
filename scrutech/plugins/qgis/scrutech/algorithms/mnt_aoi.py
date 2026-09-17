"""« MNT de la zone (IGN) »: the IGN digital terrain model of an extent, ready for écobuage.

Loops over tiles of the extent, downloads each from the Géoplateforme (LiDAR HD, RGE ALTI in its
gaps) and mosaics them into one Lambert-93 GeoTIFF (``core.sources.fetch_mnt``, run in the
external Python like the other engines).
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterDestination,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python


class MntFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Download and mosaic the IGN DEM (LiDAR HD, RGE ALTI fallback) over an extent."""

    EXTENT = "EXTENT"
    RESOLUTION = "RESOLUTION"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "mnt_aoi"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("MNT de la zone (IGN LiDAR HD)")

    def group(self) -> str:
        return self.tr("1 · Préparer l'emprise")

    def groupId(self) -> str:  # noqa: N802
        return "preparer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Télécharge le <b>modèle numérique de terrain</b> (altitude du sol) de la zone "
            "depuis l'IGN : le LiDAR HD là où il existe, complété par le RGE ALTI ailleurs. La "
            "zone est découpée en tuiles, téléchargées une à une puis assemblées en un seul "
            "GeoTIFF en Lambert-93.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : de préférence une petite zone (une commune, un massif).<br>"
            "2. Résolution : 5 m par défaut ; 1 m pour un petit secteur, 10 à 25 m pour une "
            "zone plus large.<br>"
            "3. Exécuter.</p>"
            "<p><b>Résultat</b><br>Le MNT, chargé dans le projet. Il sert directement à "
            "« ④ Aptitude à l'écobuage » et aux zones humides de « Priorisation écologique "
            "(Biotrame) ».</p>"
            "<p><b>Bon à savoir</b><br>Limite : 25 millions de pixels (par exemple 25 × 25 km à "
            "5 m). L'écobuage télécharge ce MNT tout seul si vous ne lui en donnez pas.</p>"
        )

    def createInstance(self) -> MntFromAoiAlgorithm:  # noqa: N802
        return MntFromAoiAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("data")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Résolution (m) : 5 conseillé"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=5.0,
                minValue=0.5,
                maxValue=100.0,
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT, self.tr("MNT de la zone"))
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(
                self.tr("La zone d'étude est vide : choisissez une emprise.")
            )
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        out_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "mnt_aoi",
            "bbox": list(bbox),
            "resolution": self.parameterAsDouble(parameters, self.RESOLUTION, context),
            "out_path": out_path,
        }
        try:
            payload = run_spec(
                python_exe, "vegevigie.qgis_runner", spec, Path(out_path).parent, feedback
            )
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"MNT : {payload.get('mnt_tiles')} tuile(s), {payload.get('mnt_coverage_pct')} % de la "
            f"zone couverte, résolution {payload.get('mnt_resolution')} m."
        )
        return {self.OUTPUT: out_path}
