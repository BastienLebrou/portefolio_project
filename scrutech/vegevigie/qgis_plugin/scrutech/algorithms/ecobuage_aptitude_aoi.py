"""④ Écobuage from an extent + a DEM: aptitude with no criterion rasters to prepare.

Draw an extent, point at a DEM (.tif), hit Run. ScruTech derives slope (from the DEM),
accessibility (BD TOPO roads) and exclusions (BD TOPO buildings) for the emprise and scores
controlled-burn aptitude. Optionally feed VegeVigie trend/drought rasters to add the
vegetation criteria (combustible / embroussaillement). Needs the external Python + internet.
"""

from __future__ import annotations

import os
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._layers import queue_layer
from ._venv import python_param, require_python


class EcobuageAptitudeFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Écobuage aptitude derived from an extent + a DEM (slope/access/exclusions auto)."""

    EXTENT = "EXTENT"
    MNT = "MNT"
    RESOLUTION = "RESOLUTION"
    VEG_TREND = "VEG_TREND"
    VEG_DROUGHT = "VEG_DROUGHT"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "ecobuage_aptitude_aoi"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("④ Aptitude à l'écobuage")

    def group(self) -> str:
        return self.tr("2 · Analyser une emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Note chaque endroit de 0 à 100 selon son <b>aptitude au brûlage dirigé</b> "
            "(écobuage) et le range en 3 classes : prioritaire, à étudier, à exclure. La pente "
            "vient du MNT ; les routes (accès) et les bâtiments (exclusions) sont téléchargés "
            "automatiquement.</p>"
            "<p><b>Avant de lancer</b><br>"
            "1. Avoir lancé « 0 · Démarrer ici ▸ Vérifier et installer ScruTech ».<br>"
            "2. Une connexion internet.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude.<br>"
            "2. MNT (facultatif) : laissez vide et le MNT IGN de la zone (LiDAR HD, complété "
            "par le RGE ALTI) est téléchargé automatiquement ; ou choisissez votre propre MNT "
            ".tif en Lambert-93.<br>"
            "3. Facultatif, pour une meilleure note : les couches de tendance et de sécheresse "
            "produites par ① VegeVigie sur la même zone.<br>"
            "4. Exécuter.</p>"
            "<p><b>Résultat</b><br>Deux rasters stylés : l'aptitude (0 à 100) et les classes "
            "(0 à exclure, 1 à étudier, 2 prioritaire).</p>"
            "<p><b>Bon à savoir</b><br>Sans les couches VegeVigie, la note repose seulement sur "
            "la pente, l'accès et les exclusions. Le téléchargement automatique du MNT convient "
            "aux petites zones (jusqu'à 25 × 25 km). Le résultat oriente une visite de "
            "terrain ; il ne remplace pas l'autorisation préfectorale.</p>"
        )

    def createInstance(self) -> EcobuageAptitudeFromAoiAlgorithm:  # noqa: N802
        return EcobuageAptitudeFromAoiAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("ecobuage")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Zone d'étude (emprise)"))
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.MNT,
                self.tr("MNT .tif en Lambert-93 (facultatif : vide = MNT IGN téléchargé)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,  # may come from the SCRUTECH_MNT environment variable
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Résolution d'analyse (m)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=25,
                minValue=5,
                maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_TREND,
                self.tr("Tendance VegeVigie (facultatif, pour l'embroussaillement)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_DROUGHT,
                self.tr("Sécheresse VegeVigie (facultatif, pour le combustible)"),
                optional=True,
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
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        mnt_path = self._resolve_mnt(parameters, context)
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "ecobuage_aoi",
            "bbox": list(bbox),
            "mnt_path": mnt_path,
            "resolution": resolution,
            "out_folder": str(out_folder),
            "veg_trend_tif": self._raster_source(parameters, self.VEG_TREND, context),
            "veg_drought_tif": self._raster_source(parameters, self.VEG_DROUGHT, context),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"Écobuage : prioritaire {payload.get('n_prioritaire', 0)} | "
            f"à étudier {payload.get('n_a_etudier', 0)} | "
            f"à exclure {payload.get('n_a_exclure', 0)} | critères : {payload.get('criteria')}"
        )
        self._queue_layers(payload, context)
        return {
            "APTITUDE": payload.get("aptitude_path"),
            "CLASSES": payload.get("classes_path"),
            "MNT": payload.get("mnt_path"),
        }

    # --- helpers -------------------------------------------------------------
    def _resolve_mnt(self, parameters, context) -> str | None:
        """The DEM to use, or None: the engine then downloads the IGN DEM of the zone."""
        mnt = self.parameterAsString(parameters, self.MNT, context).strip()
        if not mnt:
            mnt = os.environ.get("SCRUTECH_MNT", "").strip()
        if not mnt:
            return None
        remote = mnt.startswith(("http://", "https://", "/vsi"))  # COG read in place
        if not (remote or Path(mnt).exists()):
            raise QgsProcessingException(
                self.tr(
                    "MNT introuvable : {}. Laissez le champ vide pour télécharger le "
                    "MNT IGN de la zone."
                ).format(mnt)
            )
        return mnt

    def _raster_source(self, parameters, name, context) -> str | None:
        layer = self.parameterAsRasterLayer(parameters, name, context)
        return layer.source() if layer is not None else None

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_ecobuage"
        return Path(value)

    def _queue_layers(self, payload: dict, context) -> None:
        from ._styles import ecobuage_aptitude_qml, ecobuage_classes_qml

        mnt = payload.get("mnt_path")
        if mnt and Path(mnt).name == "mnt_ign.tif":  # downloaded for this run: show it
            queue_layer(context, mnt, "Écobuage : MNT IGN de la zone")
        if payload.get("aptitude_path"):
            queue_layer(
                context,
                payload["aptitude_path"],
                "Écobuage : aptitude (0-100)",
                ecobuage_aptitude_qml(),
            )
        if payload.get("classes_path"):
            queue_layer(
                context, payload["classes_path"], "Écobuage : classes", ecobuage_classes_qml()
            )
