"""Stage 4: NDVI-anomaly drought stress + VCI rasters and timeline for a run folder."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputRasterLayer,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class ComputeDroughtAlgorithm(ScruTechAlgorithmBase):
    """Drought stress: standardized NDVI anomaly, minimum VCI and AOI timeline."""

    ANOMALY = "ANOMALY"
    MIN_VCI = "MIN_VCI"
    TIMELINE = "TIMELINE"
    RUN_FOLDER_OUT = "RUN_FOLDER_OUT"

    def name(self) -> str:
        return "compute_drought"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("4 — Compute drought stress")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Compare each month's NDVI to the pixel's own monthly climatology: mean "
            "standardized anomaly (drought exposure) and worst Vegetation Condition "
            "Index rasters, plus the AOI-mean anomaly timeline (parquet). Uses the "
            "composites of a run folder; runs offline once they exist."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.init_downstream_parameters()
        self.addOutput(
            QgsProcessingOutputRasterLayer(self.ANOMALY, self.tr("Drought — mean NDVI anomaly"))
        )
        self.addOutput(
            QgsProcessingOutputRasterLayer(self.MIN_VCI, self.tr("Drought — minimum VCI"))
        )
        self.addOutput(
            QgsProcessingOutputFile(self.TIMELINE, self.tr("Drought timeline (parquet)"))
        )
        self.addOutput(QgsProcessingOutputFolder(self.RUN_FOLDER_OUT, self.tr("Run folder")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        payload, run_folder = self.run_downstream(
            protocol.STAGE_DROUGHT, parameters, context, feedback
        )
        artifacts = payload.get("artifacts", {})
        driest = payload.get("meta", {}).get("driest_month")
        if driest:
            feedback.pushInfo(self.tr("Driest month (lowest AOI-mean anomaly): {}").format(driest))
        self.queue_layer(
            context, artifacts.get("anomaly"), "ScruTech drought (NDVI anomaly)", "drought_anomaly"
        )
        self.queue_layer(
            context, artifacts.get("min_vci"), "ScruTech drought (min VCI)", "drought_vci"
        )
        return {
            self.ANOMALY: artifacts.get("anomaly"),
            self.MIN_VCI: artifacts.get("min_vci"),
            self.TIMELINE: artifacts.get("timeline"),
            self.RUN_FOLDER_OUT: str(run_folder),
        }
