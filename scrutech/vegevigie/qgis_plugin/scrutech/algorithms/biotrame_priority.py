"""Biotrame algorithm: hexagonal ecological-priority mesh from an extent alone.

Draw an extent, hit Run. ScruTech builds an H3 hexagon mesh over the emprise, fetches the
biodiversity reservoirs (Natura 2000 / ZNIEFF) for it, and scores each hexagon's need for
ecological action by crossing enjeu × connectivité (× dégradation if a VegeVigie trend
raster is supplied). **No input layers** — just a study area.

Needs the VegeVigie stack + internet (Géoplateforme WFS), so it runs in the external
interpreter (auto-detected).
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
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


class BiotramePriorityAlgorithm(QgsProcessingAlgorithm):
    """Hexagonal ecological-priority mesh (enjeu × connectivité × dégradation)."""

    EXTENT = "EXTENT"
    RESOLUTION = "RESOLUTION"
    VEG_TREND = "VEG_TREND"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "biotrame_priority"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Priorisation écologique (biotrame, emprise seule)")

    def group(self) -> str:
        return self.tr("Biotrame — priorisation écologique")

    def groupId(self) -> str:  # noqa: N802
        return "biotrame"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Build an H3 hexagon mesh over the extent and score each cell's need for "
            "ecological action, crossing enjeu (reservoir overlap — Natura 2000 / ZNIEFF), "
            "connectivité (proximity to reservoirs) and — if a VegeVigie trend raster is "
            "given — dégradation (browning). No input layers: just an area. Output is a "
            "hexagon layer with a 0-100 score and a 3-class ranking (candidates for "
            "restoration / compensation). Needs internet + the VegeVigie interpreter."
        )

    def createInstance(self) -> BiotramePriorityAlgorithm:  # noqa: N802
        return BiotramePriorityAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("vegevigie")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Area of interest (extent)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION, self.tr("H3 resolution (7 ≈ 5 km², 8 ≈ 0.7 km², 9 ≈ 0.1 km²)"),
                type=_compat.NUMBER_INTEGER, defaultValue=8, minValue=5, maxValue=10,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.VEG_TREND, self.tr("VegeVigie trend raster (optional — dégradation axis)"),
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
        out_folder = self._resolve_output_folder(parameters, context)

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr("No VegeVigie interpreter found. Point 'Python executable' at the "
                        "project venv (needs geopandas + h3).")
            )

        from ._external import run_spec

        spec = {
            "task": "biotrame_aoi",
            "bbox": list(bbox),
            "resolution": resolution,
            "out_folder": str(out_folder),
            "veg_trend_tif": self._raster_source(parameters, self.VEG_TREND, context),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"Biotrame — {payload.get('n_prioritaire', 0)} prioritaires / "
            f"{payload.get('n_hexagons', 0)} hexagones | "
            f"réservoirs: {payload.get('n_reservoirs', 0)} | axes: {payload.get('axes')}"
        )
        self._queue_layers(payload, context)
        return {"MESH": payload.get("geojson_path"), "PARQUET": payload.get("parquet_path")}

    # --- helpers -------------------------------------------------------------
    def _raster_source(self, parameters, name, context) -> str | None:
        layer = self.parameterAsRasterLayer(parameters, name, context)
        return layer.source() if layer is not None else None

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_biotrame"
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
        path = payload.get("geojson_path")
        if path:
            label = "Biotrame — priorisation écologique"
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
