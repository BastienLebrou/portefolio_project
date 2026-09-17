"""Write the ScruTech visual report of an area (one HTML page) and open it in the browser.

The external Python reads the outputs cached for the area and writes a self-contained page:
key figures, a map, plain-French sentences. The plugin sends its own QML styles so the page
legends match QGIS. No server to start, so nothing can hang on "CONNECTING".
"""

from __future__ import annotations

import tempfile
import webbrowser
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFileDestination,
)
from qgis.PyQt.QtCore import QCoreApplication

from ._styles import report_styles
from ._venv import python_param, require_python


class ReportLaunchAlgorithm(QgsProcessingAlgorithm):
    """Write and open the HTML report of an area of interest."""

    EXTENT = "EXTENT"
    OUTPUT = "OUTPUT"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "report_launch"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Rapport visuel de la zone (page web)")

    def group(self) -> str:
        return self.tr("4 · Consulter les résultats")

    def groupId(self) -> str:  # noqa: N802
        return "restituer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Crée une <b>page web de synthèse</b> de la zone et l'ouvre dans votre "
            "navigateur : les chiffres clés, une carte avec les couches à cocher et des phrases "
            "qui expliquent les résultats de chaque analyse déjà faite (VegeVigie, PAFF, "
            "écobuage, Biotrame, AlphaEarth).</p>"
            "<p><b>Avant de lancer</b><br>Avoir analysé la zone avec au moins un outil du "
            "groupe 2.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : <b>la même emprise</b> que celle des analyses.<br>"
            "2. Rapport : laissez vide pour un fichier temporaire, ou choisissez où "
            "l'enregistrer.<br>"
            "3. Exécuter : la page s'ouvre dans le navigateur.</p>"
            "<p><b>Bon à savoir</b><br>La page est un simple fichier .html : il s'envoie par mail "
            "et s'imprime en PDF depuis le navigateur. Les couleurs et les légendes sont celles "
            "de QGIS. Seule la carte a besoin d'internet. Relancez l'outil après une nouvelle "
            "analyse pour mettre la page à jour.</p>"
        )

    def createInstance(self) -> ReportLaunchAlgorithm:  # noqa: N802
        return ReportLaunchAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Zone d'étude (la même emprise que les analyses)")
            )
        )
        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT, self.tr("Rapport"), fileFilter="Page web (*.html)"
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))

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
        bbox = [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()]
        out_path = self.parameterAsFileOutput(parameters, self.OUTPUT, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {"task": "report", "bbox": bbox, "out_path": out_path, "styles": report_styles()}
        work = Path(tempfile.gettempdir()) / "scrutech_report"
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, work, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        html_path = Path(payload["html_path"])
        feedback.pushInfo(f"Rapport ({', '.join(payload.get('tools', []))}) : {html_path}")
        webbrowser.open(html_path.as_uri())
        return {self.OUTPUT: str(html_path)}
