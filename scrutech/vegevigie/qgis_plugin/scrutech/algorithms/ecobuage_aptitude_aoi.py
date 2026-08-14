"""AOI-only écobuage algorithm: aptitude from a study area + a DEM alone.

Draw an extent, point at a DEM (.tif), hit Run. ScruTech derives slope (from the DEM),
accessibility (BD TOPO roads) and exclusions (BD TOPO buildings) for the emprise and scores
controlled-burn aptitude — **no criterion rasters to prepare**. Optionally feed VegeVigie
trend/drought rasters to add the vegetation criteria (combustible / embroussaillement).

Needs the VegeVigie stack + internet (BD TOPO), so it runs in the external interpreter.
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
        return self.tr("Aptitude à l'écobuage depuis une emprise (AOI + MNT)")

    def group(self) -> str:
        return self.tr("Écobuage — pastoral / fire")

    def groupId(self) -> str:  # noqa: N802
        return "ecobuage"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Controlled-burn aptitude from a study area ALONE: slope (from the DEM), "
            "accessibility (BD TOPO roads) and exclusions (BD TOPO buildings) are derived for "
            "the extent — no criterion rasters to prepare. Optionally add VegeVigie trend / "
            "drought rasters for the vegetation criteria. Outputs a 0-100 aptitude raster and "
            "a 3-class raster. Needs internet + the VegeVigie interpreter.\n\n"
            "Set the DEM path, or leave it empty to use the SCRUTECH_MNT environment variable."
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
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Area of interest (extent)"))
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.MNT, self.tr("DEM / MNT (.tif) — empty = SCRUTECH_MNT env var"),
                behavior=_compat.FILE_BEHAVIOR_FILE, optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION, self.tr("Analysis resolution (m)"),
                type=_compat.NUMBER_INTEGER, defaultValue=25, minValue=5, maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_TREND, self.tr("VegeVigie trend raster (optional — embroussaillement)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_DROUGHT, self.tr("VegeVigie drought raster (optional — combustible)"),
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the VegeVigie stack (auto-detected if empty)"),
                behavior=_compat.FILE_BEHAVIOR_FILE, optional=True,
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
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(self.tr("The extent is empty."))
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        mnt_path = self._resolve_mnt(parameters, context)
        out_folder = self._resolve_output_folder(parameters, context)

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr("No VegeVigie interpreter found. Point 'Python executable' at the "
                        "project venv (needs rasterio + geopandas).")
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
            f"Écobuage — prioritaire: {payload.get('n_prioritaire', 0)} | "
            f"à étudier: {payload.get('n_a_etudier', 0)} | "
            f"à exclure: {payload.get('n_a_exclure', 0)} | criteria: {payload.get('criteria')}"
        )
        self._write_styles(payload, feedback)
        self._queue_layers(payload, context)
        return {"APTITUDE": payload.get("aptitude_path"), "CLASSES": payload.get("classes_path")}

    def _write_styles(self, payload: dict, feedback) -> None:
        from ._styles import ecobuage_aptitude_qml, ecobuage_classes_qml

        pairs = [
            (payload.get("aptitude_path"), ecobuage_aptitude_qml()),
            (payload.get("classes_path"), ecobuage_classes_qml()),
        ]
        for path, qml in pairs:
            if not path:
                continue
            try:
                Path(path).with_suffix(".qml").write_text(qml, encoding="utf-8")
            except OSError as exc:
                feedback.pushInfo(f"Could not write style for {path}: {exc}")

    # --- helpers -------------------------------------------------------------
    def _resolve_mnt(self, parameters, context) -> str:
        mnt = self.parameterAsString(parameters, self.MNT, context).strip()
        if not mnt:
            mnt = os.environ.get("SCRUTECH_MNT", "").strip()
        if not mnt or not Path(mnt).exists():
            raise QgsProcessingException(
                self.tr("No DEM found. Set the DEM (.tif) parameter or the SCRUTECH_MNT "
                        "environment variable to an existing file.")
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

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"VegeVigie interpreter: {python_exe}")
        return python_exe

    def _queue_layers(self, payload: dict, context) -> None:
        pairs = [
            (payload.get("aptitude_path"), "Écobuage — aptitude (0-100)"),
            (payload.get("classes_path"), "Écobuage — classes (0/1/2)"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
