"""Helper algorithm: load French commune boundaries as a zones layer.

Gives the user a ready-made polygon layer to feed into the "Analyze extent"
algorithm's optional *Zones* input (for per-commune ranking).
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorDestination,
)
from qgis.PyQt.QtCore import QCoreApplication


class LoadCommunesAlgorithm(QgsProcessingAlgorithm):
    """Download a département's commune polygons to a GeoPackage."""

    DEPARTEMENT = "DEPARTEMENT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "load_communes"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Load commune boundaries (zones)")

    def group(self) -> str:
        return self.tr("Data")

    def groupId(self) -> str:  # noqa: N802
        return "data"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Download the commune polygons of a French département (default 07, Ardèche) "
            "to use as the Zones input of 'Analyze extent'. Needs internet access."
        )

    def createInstance(self) -> LoadCommunesAlgorithm:  # noqa: N802
        return LoadCommunesAlgorithm()

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterString(
                self.DEPARTEMENT, self.tr("Département code"), defaultValue="07"
            )
        )
        self.addParameter(QgsProcessingParameterVectorDestination(self.OUTPUT, self.tr("Communes")))

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from ..dependencies import install_hint, missing_dependencies

        missing = missing_dependencies()
        if missing:
            raise QgsProcessingException(install_hint(missing))

        from vegevigie.aoi import fetch_communes

        dept = self.parameterAsString(parameters, self.DEPARTEMENT, context).strip()
        out_path = Path(self.parameterAsOutputLayer(parameters, self.OUTPUT, context))

        feedback.pushInfo(f"Fetching commune boundaries for département {dept}…")
        try:
            communes = fetch_communes(dept)
        except Exception as exc:  # noqa: BLE001
            raise QgsProcessingException(f"Could not fetch communes for {dept}: {exc}") from exc

        out_path.parent.mkdir(parents=True, exist_ok=True)
        communes.to_file(out_path, driver="GPKG")
        feedback.pushInfo(f"Wrote {len(communes)} communes to {out_path}")
        return {self.OUTPUT: str(out_path)}
