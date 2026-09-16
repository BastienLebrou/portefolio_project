"""GeoAI: zero-shot object segmentation of a raster with Meta's SAM (experimental).

Pick any raster layer (Sentinel-2 composite, aerial ortho, a VegeVigie output…), hit Run:
ScruTech segments it into georeferenced objects with the Segment Anything Model, no
training needed. Needs the optional 'geoai' extra (segment-geospatial + torch) in the
external interpreter: heavy, so this never runs in QGIS's own Python.

On first run it downloads the SAM checkpoint (~375 MB, Apache-2.0, Meta AI) from the
official facebookresearch source into ``~/.scrutech/models`` and pins its checksum for
reuse; see ``vegevigie.geoai_segment`` for the security rationale (TOFU, why not a
fabricated "official" hash). Every subsequent run is fully offline.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python


class GeoaiSegmentAlgorithm(QgsProcessingAlgorithm):
    """Segment any raster into objects with a locally-downloaded open model (SAM)."""

    INPUT = "INPUT"
    POINTS_PER_SIDE = "POINTS_PER_SIDE"
    MIN_AREA = "MIN_AREA"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "geoai_segment"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Segmenter une image en objets (SAM)")

    def group(self) -> str:
        return self.tr("6 · GeoAI (expérimental)")

    def groupId(self) -> str:  # noqa: N802
        return "geoai"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p><b>Expérimental.</b> Découpe automatiquement une image (orthophoto, image "
            "satellite, résultat VegeVigie…) en <b>objets</b> : parcelles, bâtiments, "
            "bosquets… avec le modèle ouvert Segment Anything (SAM) de Meta, sans "
            "entraînement.</p>"
            "<p><b>Avant de lancer</b><br>Ce module n'est <b>pas installé par défaut</b> : il "
            "demande torch, qui pèse plusieurs Go, et « Vérifier et installer ScruTech » ne "
            "l'installe pas encore. Il est réservé aux utilisateurs avancés (extra « geoai » "
            "du moteur).</p>"
            "<p><b>Étapes</b><br>"
            "1. Image à segmenter : une couche raster du projet (commencez par une petite "
            "image).<br>"
            "2. Exécuter.</p>"
            "<p><b>Résultat</b><br>Une couche de polygones (un par objet) et le masque "
            "raster.</p>"
            "<p><b>Bon à savoir</b><br>Le premier lancement télécharge le modèle (environ "
            "375 Mo, licence Apache-2.0, source officielle de Meta) dans ~/.scrutech/models et "
            "contrôle son empreinte à chaque usage ; ensuite tout fonctionne hors ligne, sans "
            "clé ni quota.</p>"
        )

    def createInstance(self) -> GeoaiSegmentAlgorithm:  # noqa: N802
        return GeoaiSegmentAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("geoai")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterRasterLayer(self.INPUT, self.tr("Image à segmenter"))
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterNumber(
                    self.POINTS_PER_SIDE,
                    self.tr("Densité de la grille de points (par côté)"),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=32,
                    minValue=8,
                    maxValue=64,
                )
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterNumber(
                    self.MIN_AREA,
                    self.tr("Taille minimale d'un objet (pixels)"),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=100,
                    minValue=0,
                    maxValue=100000,
                )
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
        raster = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        if raster is None:
            raise QgsProcessingException(self.tr("Choisissez une image à segmenter."))
        points_per_side = self.parameterAsInt(parameters, self.POINTS_PER_SIDE, context)
        min_area = self.parameterAsInt(parameters, self.MIN_AREA, context)
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )

        from ._external import run_spec

        spec = {
            "task": "geoai_segment",
            "raster_path": raster.source(),
            "points_per_side": points_per_side,
            "min_mask_region_area": min_area,
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(f"GeoAI : {payload.get('n_objects', 0)} objet(s) segmenté(s).")
        self._queue_layers(payload, context)
        return {"MASK": payload.get("mask_path"), "VECTOR": payload.get("vector_path")}

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_geoai"
        return Path(value)

    def _queue_layers(self, payload: dict, context) -> None:
        pairs = [
            (payload.get("vector_path"), "GeoAI : objets segmentés (SAM)"),
            (payload.get("mask_path"), "GeoAI : masque (SAM)"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
