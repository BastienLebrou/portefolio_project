"""« Communes d'un département »: a ready-made zones layer, straight from geo.api.gouv.fr.

Native QGIS network + OGR only, so it works before the external Python is installed.
"""

from __future__ import annotations

from qgis.core import (
    QgsBlockingNetworkRequest,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterString,
    QgsProcessingUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest

from . import _qgis_compat as _compat

# ponytail: geo.api.gouv.fr only; core.aoi's france-geojson mirror is not wired in here.
_URL = (
    "https://geo.api.gouv.fr/communes?codeDepartement={}"
    "&fields=code,nom&format=geojson&geometry=contour"
)


class LoadCommunesAlgorithm(QgsProcessingAlgorithm):
    """Download a département's commune polygons."""

    DEPARTEMENT = "DEPARTEMENT"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "load_communes"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Communes d'un département")

    def group(self) -> str:
        return self.tr("1 · Préparer l'emprise")

    def groupId(self) -> str:  # noqa: N802
        return "preparer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Télécharge les <b>limites des communes</b> d'un département. La couche obtenue "
            "sert à choisir une zone d'étude (bouton ▾ ▸ emprise d'une couche) ou à obtenir "
            "un classement par commune dans ① VegeVigie.</p>"
            "<p><b>Étapes</b><br>1. Code du département : 07, 69, 2A…<br>2. Exécuter.</p>"
            "<p><b>Bon à savoir</b><br>Fonctionne tout de suite, même avant d'avoir installé "
            "le Python de ScruTech. Source : geo.api.gouv.fr (données officielles, internet "
            "requis).</p>"
        )

    def createInstance(self) -> LoadCommunesAlgorithm:  # noqa: N802
        return LoadCommunesAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("data")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterString(
                self.DEPARTEMENT, self.tr("Code du département (ex. 07, 69, 2A)"), defaultValue="07"
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT, self.tr("Communes"), _compat.SOURCE_VECTOR_POLYGON
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        dept = self.parameterAsString(parameters, self.DEPARTEMENT, context).strip().upper()
        if dept.isdigit():
            dept = dept.zfill(2)

        request = QgsBlockingNetworkRequest()
        error = request.get(QNetworkRequest(QUrl(_URL.format(dept))), False, feedback)
        if error != _compat.NETWORK_NO_ERROR:
            raise QgsProcessingException(
                self.tr(
                    "Impossible de télécharger les communes du département {} : {}. Vérifiez la "
                    "connexion internet (et le proxy dans Préférences ▸ Options ▸ Réseau)."
                ).format(dept, request.errorMessage())
            )
        path = QgsProcessingUtils.generateTempFilename("communes.geojson")
        with open(path, "wb") as fh:
            fh.write(bytes(request.reply().content()))

        layer = QgsVectorLayer(path, "communes", "ogr")
        if not layer.isValid() or layer.featureCount() == 0:
            raise QgsProcessingException(
                self.tr(
                    "Aucune commune trouvée pour le département « {} ». Vérifiez le code "
                    "(ex. 07, 69, 2A)."
                ).format(dept)
            )
        sink, dest_id = self.parameterAsSink(
            parameters, self.OUTPUT, context, layer.fields(), layer.wkbType(), layer.crs()
        )
        if sink is None:
            raise QgsProcessingException(self.tr("Impossible de créer la couche de sortie."))
        for feature in layer.getFeatures():
            sink.addFeature(feature, _compat.SINK_FAST_INSERT)
        feedback.pushInfo(
            self.tr("{} communes téléchargées pour le département {}.").format(
                layer.featureCount(), dept
            )
        )
        return {self.OUTPUT: dest_id}
