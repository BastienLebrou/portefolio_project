"""Stage 2: datacube + cloud masking + NDVI monthly composites for a run folder."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputNumber,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class BuildCompositesAlgorithm(ScruTechAlgorithmBase):
    """Build the gap-aware monthly NDVI composites (the heavy download stage)."""

    MONTHLY = "MONTHLY"
    MONTHS = "MONTHS"
    RUN_FOLDER_OUT = "RUN_FOLDER_OUT"

    def name(self) -> str:
        return "build_composites"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("2 — Build NDVI composites")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Load the Sentinel-2 datacube for a run folder (from '1 — Search scenes'), "
            "mask clouds with the SCL band, compute NDVI and reduce it to gap-aware "
            "monthly median composites (zarr). This is the stage that downloads pixels — "
            "it needs internet access and is skipped when already up to date."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.init_downstream_parameters()
        self.addOutput(
            QgsProcessingOutputFile(self.MONTHLY, self.tr("Monthly NDVI composites (zarr)"))
        )
        self.addOutput(QgsProcessingOutputNumber(self.MONTHS, self.tr("Months in the series")))
        self.addOutput(QgsProcessingOutputFolder(self.RUN_FOLDER_OUT, self.tr("Run folder")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        payload, run_folder = self.run_downstream(
            protocol.STAGE_COMPOSITES, parameters, context, feedback
        )
        return {
            self.MONTHLY: payload.get("artifacts", {}).get("monthly"),
            self.MONTHS: int(payload.get("meta", {}).get("months", 0)),
            self.RUN_FOLDER_OUT: str(run_folder),
        }
