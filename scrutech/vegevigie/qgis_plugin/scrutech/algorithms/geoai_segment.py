"""GeoAI algorithm: zero-shot object segmentation of a raster with Meta's SAM.

Experimental. Pick any raster layer (Sentinel-2 composite, aerial ortho, a VegeVigie
output…), hit Run — ScruTech segments it into georeferenced objects with the Segment
Anything Model, no training needed. Needs the optional 'geoai' extra (segment-geospatial +
torch) in the external interpreter — heavy, so this never runs in-process in QGIS's Python.

On first run it downloads the SAM checkpoint (~375 MB, Apache-2.0, Meta AI) from the
official facebookresearch source into ``~/.scrutech/models`` and pins its checksum for
reuse — see ``vegevigie.geoai_segment`` for the full security rationale (TOFU, why not a
fabricated "official" hash). Every subsequent run is fully offline.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


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
        return self.tr("Segment anything (SAM, experimental)")

    def group(self) -> str:
        return self.tr("7 · GeoAI (modèles ouverts)")

    def groupId(self) -> str:  # noqa: N802
        return "geoai"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Zero-shot segmentation of any raster into georeferenced objects, using Meta's "
            "Segment Anything Model (SAM) — no training, no labels needed. EXPERIMENTAL.\n\n"
            "First run downloads the SAM ViT-B checkpoint (~375 MB, Apache-2.0 license) from "
            "the official dl.fbaipublicfiles.com source into ~/.scrutech/models and pins its "
            "checksum there for reuse — every run after that is fully offline, no API key, "
            "no cloud quota.\n\n"
            "Needs the optional 'geoai' extra (segment-geospatial + torch) installed in the "
            "'Python executable' venv — run 'uv sync --extra geoai' in scrutech/vegevigie "
            "first. Runs in an external interpreter only; never in QGIS's own Python."
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
            QgsProcessingParameterRasterLayer(self.INPUT, self.tr("Raster to segment"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.POINTS_PER_SIDE,
                self.tr("Prompt grid density (points per side)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=32,
                minValue=8,
                maxValue=64,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MIN_AREA,
                self.tr("Minimum object size (pixels)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=100,
                minValue=0,
                maxValue=100000,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr(
                    "Python executable with the 'geoai' extra (auto-detected if empty)"
                ),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, self.tr("Output folder"))
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        raster = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        if raster is None:
            raise QgsProcessingException(self.tr("No input raster."))
        points_per_side = self.parameterAsInt(parameters, self.POINTS_PER_SIDE, context)
        min_area = self.parameterAsInt(parameters, self.MIN_AREA, context)
        out_folder = self._resolve_output_folder(parameters, context)

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr(
                    "No Python interpreter found. Point 'Python executable' at a venv with "
                    "the 'geoai' extra installed (uv sync --extra geoai)."
                )
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

        feedback.pushInfo(f"GeoAI — segmented {payload.get('n_objects', 0)} object(s).")
        self._queue_layers(payload, context)
        return {"MASK": payload.get("mask_path"), "VECTOR": payload.get("vector_path")}

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_geoai"
        return Path(value)

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"GeoAI interpreter: {python_exe}")
        return python_exe

    def _queue_layers(self, payload: dict, context) -> None:
        pairs = [
            (payload.get("vector_path"), "GeoAI — segments (SAM)"),
            (payload.get("mask_path"), "GeoAI — mask raster (SAM)"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
