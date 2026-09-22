"""« Projection climatique 2035-2055 »: the future climate of a zone and where it hits hardest.

Runs ``vegevigie.projection`` in the external Python: CMIP6 climate at the zone's centre read at
the TRACC warming of each horizon, crossed with the vegetation analysed by VegeVigie (read
from the cache of the zone). Loads one exposure map per horizon and the NDVI trend extrapolated
to +10 years.
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
    QgsProcessingParameterFolderDestination,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from ._venv import python_param, require_python

_LABELS = {
    "jours_chauds": "jours à plus de 30 °C par an",
    "periode_seche": "plus longue période sans pluie (jours)",
    "jours_feu": "jours propices aux feux par an",
}


class ProjectionFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Future climate (+10 to +30 years) of an extent and its exposure maps."""

    EXTENT = "EXTENT"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "projection_climat"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Projection climatique 2035-2055 (zones les plus touchées)")

    def group(self) -> str:
        return self.tr("3 · Croiser et prioriser")

    def groupId(self) -> str:  # noqa: N802
        return "prioriser"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Le <b>climat futur de la zone</b> dans 10, 15, 20 et 30 ans (2035, 2040, 2045, "
            "2055) et les <b>secteurs qu'il touchera le plus</b>.</p>"
            "<p><b>Méthode</b><br>Des simulations climatiques de 4 modèles (CMIP6, maille de "
            "10 km) donnent, au centre de la zone, les jours à plus de 30 °C, la plus longue "
            "période sans pluie et les jours propices aux feux. Chaque indicateur est relié au "
            "réchauffement local, puis lu au niveau de réchauffement de la trajectoire de "
            "référence française (TRACC : +2 °C en 2030, +2,7 °C en 2050). La végétation "
            "analysée par ① VegeVigie situe ensuite les secteurs sensibles : déjà stressés ou en "
            "déclin, ce sont eux que le climat plus chaud et plus sec touchera en premier.</p>"
            "<p><b>Avant de lancer</b><br>De préférence, avoir analysé la même zone avec "
            "« ① Végétation » : sans elle, vous obtenez le climat futur mais pas les cartes. Une "
            "connexion internet.</p>"
            "<p><b>Résultat</b><br>Une carte d'exposition par horizon (de très faible à très "
            "forte), le NDVI en 2035 si la tendance observée continue, et un tableau des "
            "indicateurs (projection_climat.csv) avec la fourchette entre les modèles.</p>"
            "<p><b>Bon à savoir</b><br>Ce sont des ordres de grandeur, pas des prévisions : le "
            "climat est une valeur pour toute la zone (maille de 10 km). Données : Open-Meteo "
            "(licence CC BY 4.0), gratuit pour un usage non commercial, environ 3 nouvelles "
            "zones par heure ; une zone déjà projetée (ou voisine, à 10 km près) ne coûte "
            "rien.</p>"
        )

    def createInstance(self) -> ProjectionFromAoiAlgorithm:  # noqa: N802
        return ProjectionFromAoiAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Zone d'étude (la même emprise que ① Végétation)")
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Dossier de résultats")
            )
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
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "projection",
            "bbox": [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()],
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        for name, by_year in payload.get("indicators", {}).items():
            steps = " · ".join(f"{year} : {values[0]:.0f}" for year, values in by_year.items())
            feedback.pushInfo(f"{_LABELS.get(name, name)} : {steps}")
        self._queue_layers(payload.get("paths", []), context)
        return {self.OUTPUT_FOLDER: str(out_folder)}

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_projection"
        return Path(value)

    def _queue_layers(self, paths: list, context: QgsProcessingContext) -> None:
        from ._layers import queue_layer
        from ._styles import style_for

        for path in paths:
            name = Path(path).stem
            if not name.startswith(("exposition_", "ndvi_tendance_")):
                continue
            year = name.rsplit("_", 1)[-1]
            if name.startswith("ndvi_tendance_"):
                label = f"Projection : NDVI {year} si la tendance continue"
            elif year == "2025":
                label = "Projection : exposition aujourd'hui"
            else:
                label = f"Projection : exposition {year}"
            queue_layer(context, path, label, style_for(str(path)))
