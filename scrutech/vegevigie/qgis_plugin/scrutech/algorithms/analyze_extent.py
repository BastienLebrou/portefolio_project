"""① VegeVigie over an extent: vegetation trend & drought, in one run.

Draw or pick an extent, set the year window, hit Run: the engine (``vegevigie.qgis_runner``,
default task) searches Sentinel-2, builds the datacube and produces greening/browning and
drought layers, loaded straight into the project. It always runs in the external Python:
QGIS's own Python lacks the datacube stack, and installing GDAL-based packages into it
clashes with QGIS's GDAL.
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
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python


class AnalyzeExtentAlgorithm(QgsProcessingAlgorithm):
    """Full VegeVigie pipeline over a user-drawn extent, in one run."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    MAX_CLOUD = "MAX_CLOUD"
    ZONES = "ZONES"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    # --- boilerplate identity ------------------------------------------------
    def name(self) -> str:
        return "analyze_extent"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("① Végétation : tendance et sécheresse (VegeVigie)")

    def group(self) -> str:
        return self.tr("2 · Analyser une emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Mesure, pixel par pixel, si la végétation <b>verdit ou dépérit</b> au fil des "
            "années et où elle <b>souffre de la sécheresse</b>, à partir des images satellite "
            "Sentinel-2.</p>"
            "<p><b>Avant de lancer</b><br>Avoir lancé une fois « 0 · Démarrer ici ▸ Vérifier "
            "et installer ScruTech ». Une connexion internet : les images sont lues en ligne.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : bouton ▾ pour prendre l'emprise de la carte ou d'une couche, ou "
            "pour la dessiner. Commencez petit (une commune).<br>"
            "2. Années de début et de fin : une tendance est plus fiable sur plusieurs années.<br>"
            "3. Facultatif : une couche de zones (par exemple les communes, voir le groupe 1) "
            "pour obtenir un classement par zone.<br>"
            "4. Exécuter.</p>"
            "<p><b>Résultat</b><br>Des couches stylées dans le projet : tendance (verdit ou "
            "dépérit), année de rupture, anomalie de sécheresse et, si des zones sont données, "
            "un tableau par zone.</p>"
            "<p><b>Bon à savoir</b><br>Plus la zone et la période sont grandes, plus le calcul "
            "est long (de quelques minutes à plus d'une heure). 60 m de résolution est un bon "
            "compromis ; 10 m est réservé aux petites zones. Les endroits trop nuageux restent "
            "vides : rien n'est inventé.</p>"
        )

    def createInstance(self) -> AnalyzeExtentAlgorithm:  # noqa: N802
        return AnalyzeExtentAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    # --- parameters ----------------------------------------------------------
    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.START_YEAR,
                self.tr("Année de début"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.END_YEAR,
                self.tr("Année de fin"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Résolution (m) : 60 conseillé, 10 pour une petite zone"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=60,
                minValue=10,
                maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_CLOUD,
                self.tr("Nuages maximum par image (%)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=60,
                minValue=0,
                maxValue=100,
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ZONES,
                self.tr("Zones pour un classement (facultatif, ex. communes)"),
                optional=True,
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Dossier de résultats")
            )
        )

    # --- run -----------------------------------------------------------------
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

        start = self.parameterAsInt(parameters, self.START_YEAR, context)
        end = self.parameterAsInt(parameters, self.END_YEAR, context)
        if start > end:
            raise QgsProcessingException(
                self.tr("L'année de début doit être antérieure ou égale à l'année de fin.")
            )
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )
        zones_path = self._zones_to_path(parameters, context, out_folder, feedback)

        from ._external import run_spec

        spec = {
            "bbox": list(bbox),
            "start": start,
            "end": end,
            "resolution": self.parameterAsInt(parameters, self.RESOLUTION, context),
            "max_cloud": self.parameterAsInt(parameters, self.MAX_CLOUD, context),
            "out_folder": str(out_folder),
            "zones_path": str(zones_path) if zones_path else None,
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(_explain(str(exc))) from exc

        scenes = int(payload.get("scene_count", 0))
        if scenes == 0:
            feedback.reportError(
                self.tr(
                    "Aucune image Sentinel-2 trouvée pour cette zone et ces années. Élargissez "
                    "la période ou augmentez le seuil de nuages."
                )
            )
        self._write_styles(payload, feedback)
        self._queue_layers(payload, context)
        return {
            "TREND": payload.get("trend_tif"),
            "DROUGHT": payload.get("drought_tif"),
            "ZONAL": payload.get("zonal_parquet"),
            "SCENES": scenes,
        }

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech"
        return Path(value)

    def _write_styles(self, payload: dict, feedback) -> None:
        """Drop a sibling .qml next to each raster so QGIS applies the ScruTech style."""
        from ._styles import drought_qml, trend_qml

        for key, qml in (("trend_tif", trend_qml()), ("drought_tif", drought_qml())):
            tif = payload.get(key)
            if not tif:
                continue
            try:
                Path(tif).with_suffix(".qml").write_text(qml, encoding="utf-8")
            except OSError as exc:
                feedback.pushInfo(f"Style non écrit pour {tif} : {exc}")

    def _zones_to_path(self, parameters, context, out_folder, feedback) -> Path | None:
        layer = self.parameterAsVectorLayer(parameters, self.ZONES, context)
        if layer is None:
            return None
        from qgis.core import QgsVectorFileWriter

        out_folder.mkdir(parents=True, exist_ok=True)
        tmp = out_folder / "scrutech_zones.gpkg"
        QgsVectorFileWriter.writeAsVectorFormat(layer, str(tmp), "utf-8", layer.crs(), "GPKG")
        feedback.pushInfo(f"Couche de zones préparée ({layer.featureCount()} entités).")
        return tmp

    def _queue_layers(self, payload: dict, context: QgsProcessingContext) -> None:
        pairs = [
            ("trend_tif", "VegeVigie : tendance (pente de Sen)"),
            ("break_tif", "VegeVigie : année de rupture (Pettitt)"),
            ("drought_tif", "VegeVigie : sécheresse (anomalie de NDVI)"),
            ("zonal_parquet", "VegeVigie : statistiques par zone"),
        ]
        for key, label in pairs:
            path = payload.get(key)
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)


def _explain(text: str) -> str:
    """Turn a network failure on the imagery source into an actionable message."""
    if any(m in text for m in ("403", "Forbidden", "Proxy", "Max retries")):
        return (
            "Impossible de joindre Microsoft Planetary Computer (planetarycomputer.microsoft.com), "
            "qui fournit les images. Vérifiez la connexion internet, le proxy ou le pare-feu, "
            "puis relancez.\n\nErreur d'origine : " + text
        )
    return "L'analyse a échoué : " + text
