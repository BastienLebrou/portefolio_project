"""« Image aérienne de la zone (IGN) »: the IGN aerial photo of an extent, ready for SAM.

Loops over tiles of the extent, downloads each from the Géoplateforme (BD ORTHO, RGB) and
mosaics them into one Lambert-93 GeoTIFF (``core.sources.fetch_ortho``, run in the external
Python like the DEM tool).
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


class OrthoFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Download and mosaic the IGN aerial photo (BD ORTHO) over an extent."""

    EXTENT = "EXTENT"
    RESOLUTION = "RESOLUTION"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT = "OUTPUT"

    def name(self) -> str:
        return "ortho_aoi"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Image aérienne de la zone (IGN BD ORTHO)")

    def group(self) -> str:
        return self.tr("1 · Préparer l'emprise")

    def groupId(self) -> str:  # noqa: N802
        return "preparer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Télécharge la <b>photographie aérienne</b> de la zone depuis l'IGN (BD ORTHO, "
            "en couleurs, jusqu'à 20 cm par pixel). La zone est découpée en tuiles, "
            "téléchargées une à une puis assemblées en un seul GeoTIFF en Lambert-93.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé « 0 · Démarrer ici ▸ Vérifier et "
            "installer ScruTech ». Une connexion internet.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : une petite zone (un quartier, une parcelle, un massif).<br>"
            "2. Taille des pixels : 0,5 m par défaut ; 0,2 m pour distinguer des arbres isolés "
            "ou des toitures, 1 à 2 m pour une zone plus large.<br>"
            "3. Exécuter.</p>"
            "<p><b>Résultat</b><br>L'image, chargée dans le projet. Elle sert directement à "
            "« 6 · GeoAI ▸ Segmenter une image en objets (SAM) », qui a besoin de vraies "
            "couleurs à haute résolution (les images Sentinel-2 à 10 m sont trop grossières).</p>"
            "<p><b>Bon à savoir</b><br>Limite : 25 millions de pixels (par exemple 2,5 × 2,5 km "
            "à 0,5 m). Pour SAM, restez plutôt sous 2 000 × 2 000 pixels (1 × 1 km à 0,5 m) : "
            "au-delà, la segmentation devient très longue sans carte graphique. Photographies "
            "IGN : sous licence ouverte, citer « IGN, BD ORTHO ».</p>"
        )

    def createInstance(self) -> OrthoFromAoiAlgorithm:  # noqa: N802
        return OrthoFromAoiAlgorithm()

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
                self.tr("Taille des pixels (m) : 0,5 conseillé"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=0.5,
                minValue=0.2,
                maxValue=20.0,
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterRasterDestination(self.OUTPUT, self.tr("Image aérienne"))
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
        out_path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "ortho_aoi",
            "bbox": [rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()],
            "resolution": self.parameterAsDouble(parameters, self.RESOLUTION, context),
            "out_path": out_path,
        }
        try:
            payload = run_spec(
                python_exe, "vegevigie.qgis_runner", spec, Path(out_path).parent, feedback
            )
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        width, height = payload.get("ortho_px", [0, 0])
        feedback.pushInfo(
            f"Image aérienne : {width} × {height} pixels de {payload.get('ortho_resolution')} m, "
            f"{payload.get('ortho_tiles')} tuile(s)."
        )
        if width * height > 4_000_000:
            feedback.pushWarning(
                self.tr(
                    "Image de plus de 2 000 × 2 000 pixels : la segmentation SAM risque d'être "
                    "très longue. Réduisez la zone ou prenez des pixels plus grands."
                )
            )
        return {self.OUTPUT: out_path}
