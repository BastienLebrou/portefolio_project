"""Stage 3: per-pixel Mann-Kendall + Sen's slope trend rasters for a run folder."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFolder,
    QgsProcessingOutputRasterLayer,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class ComputeTrendAlgorithm(ScruTechAlgorithmBase):
    """Greening/browning trend: Sen's slope, significance class and p-value."""

    SEN_SLOPE = "SEN_SLOPE"
    TREND_CLASS = "TREND_CLASS"
    PVALUE = "PVALUE"
    RUN_FOLDER_OUT = "RUN_FOLDER_OUT"

    def name(self) -> str:
        return "compute_trend"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("3 — Compute trend (Mann-Kendall + Sen)")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Per-pixel Mann-Kendall test + Theil-Sen slope over the monthly NDVI "
            "composites of a run folder (from '2 — Build NDVI composites'). Loads the "
            "Sen's-slope and trend-class rasters; the p-value raster is written too. "
            "Runs offline once the composites exist."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.init_downstream_parameters()
        self.addOutput(
            QgsProcessingOutputRasterLayer(self.SEN_SLOPE, self.tr("Trend — Sen's slope"))
        )
        self.addOutput(
            QgsProcessingOutputRasterLayer(
                self.TREND_CLASS, self.tr("Trend — class (greening/browning)")
            )
        )
        self.addOutput(QgsProcessingOutputRasterLayer(self.PVALUE, self.tr("Trend — p-value")))
        self.addOutput(QgsProcessingOutputFolder(self.RUN_FOLDER_OUT, self.tr("Run folder")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        payload, run_folder = self.run_downstream(
            protocol.STAGE_TREND, parameters, context, feedback
        )
        artifacts = payload.get("artifacts", {})
        meta = payload.get("meta", {})
        if meta:
            feedback.pushInfo(
                self.tr("Greening pixels: {} | browning pixels: {}").format(
                    meta.get("greening_pixels", "?"), meta.get("browning_pixels", "?")
                )
            )
        self.queue_layer(
            context, artifacts.get("sen_slope"), "ScruTech trend (Sen's slope)", "trend_sen_slope"
        )
        self.queue_layer(
            context, artifacts.get("trend_class"), "ScruTech trend class", "trend_class"
        )
        return {
            self.SEN_SLOPE: artifacts.get("sen_slope"),
            self.TREND_CLASS: artifacts.get("trend_class"),
            self.PVALUE: artifacts.get("mk_pvalue"),
            self.RUN_FOLDER_OUT: str(run_folder),
        }
