"""Pipeline entry stage: STAC search over an extent → run folder + scene list.

This is the algorithm that *creates a run*: it records the AOI, year window,
resolution and cloud ceiling in the run folder's manifest, so every downstream
stage (composites, trend, drought, zonal, rank) only needs the folder. Chain the
**Run folder** output into those algorithms — in the Model Designer or by hand.
"""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingOutputNumber,
    QgsProcessingParameterExtent,
    QgsProcessingParameterNumber,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class SearchScenesAlgorithm(ScruTechAlgorithmBase):
    """Search Sentinel-2 scenes and start a ScruTech run folder."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    MAX_CLOUD = "MAX_CLOUD"
    ITEMS = "ITEMS"
    SCENE_COUNT = "SCENE_COUNT"

    def name(self) -> str:
        return "search_scenes"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("1 — Search scenes (start a run)")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Search Sentinel-2 L2A scenes over the extent and start a ScruTech run "
            "folder: the AOI, year window, resolution and cloud ceiling are recorded "
            "in the folder's manifest, so the later stages only need the folder. "
            "Feed the 'Run folder' output into '2 — Build NDVI composites'. "
            "Needs internet access to Microsoft Planetary Computer."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Area of interest (extent)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.START_YEAR,
                self.tr("Start year"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.END_YEAR,
                self.tr("End year"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Resolution (m) — used by the composites stage"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=60,
                minValue=10,
                maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_CLOUD,
                self.tr("Max scene cloud cover (%)"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=60,
                minValue=0,
                maxValue=100,
            )
        )
        self.add_python_parameter()
        self.add_force_parameter()
        self.add_output_folder_parameter()
        self.addOutput(QgsProcessingOutputFile(self.ITEMS, self.tr("Cached scene list (JSON)")))
        self.addOutput(QgsProcessingOutputNumber(self.SCENE_COUNT, self.tr("Scenes found")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        bbox = self.extent_to_bbox(parameters, self.EXTENT, context)
        out_folder = self.resolve_output_folder(parameters, context)
        python_exe = self.resolve_python(parameters, context)
        spec = protocol.build_spec(
            protocol.STAGE_SEARCH,
            str(out_folder),
            bbox=bbox,
            start=self.parameterAsInt(parameters, self.START_YEAR, context),
            end=self.parameterAsInt(parameters, self.END_YEAR, context),
            resolution=self.parameterAsInt(parameters, self.RESOLUTION, context),
            max_cloud=self.parameterAsInt(parameters, self.MAX_CLOUD, context),
            force=self.parameterAsBoolean(parameters, self.FORCE, context),
        )
        payload = self.run_spec(spec, python_exe, out_folder, feedback)

        scene_count = int(payload.get("meta", {}).get("scene_count", 0))
        if scene_count == 0:
            feedback.reportError(self.tr("No Sentinel-2 scenes found for this AOI/window."))
        return {
            self.OUTPUT_FOLDER: str(out_folder),
            self.ITEMS: payload.get("artifacts", {}).get("items"),
            self.SCENE_COUNT: scene_count,
        }
