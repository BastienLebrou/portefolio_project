"""Stage 6: rank zones by a zonal metric (DuckDB query) — the decision view."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterEnum,
    QgsProcessingParameterNumber,
)

from .. import protocol
from .base import ScruTechAlgorithmBase

METRICS = ("mean_sen_slope", "pct_greening", "pct_browning", "mean_anomaly", "min_vci")


class RankZonesAlgorithm(ScruTechAlgorithmBase):
    """Top-N zones by trend or drought metric, from the run folder's DuckDB store."""

    METRIC = "METRIC"
    ASCENDING = "ASCENDING"
    LIMIT = "LIMIT"
    CSV = "CSV"

    def name(self) -> str:
        return "rank_zones"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("6 — Rank zones")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Query the DuckDB store written by '5 — Zonal statistics' and rank the "
            "zones by a metric (greening rate, % browning, drought anomaly, worst "
            "VCI…). The ranking is shown in the log and written as CSV. Sort "
            "ascending to surface the most browning / most drought-stressed zones "
            "for negative metrics."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.add_run_folder_parameter()
        self.addParameter(
            QgsProcessingParameterEnum(
                self.METRIC, self.tr("Metric"), options=list(METRICS), defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.ASCENDING, self.tr("Smallest values first (ascending)"), defaultValue=False
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.LIMIT,
                self.tr("Number of zones to return"),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=10,
                minValue=1,
                maxValue=1000,
            )
        )
        self.add_python_parameter()
        self.add_force_parameter()
        self.addOutput(QgsProcessingOutputFile(self.CSV, self.tr("Ranking (CSV)")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        metric = METRICS[self.parameterAsEnum(parameters, self.METRIC, context)]
        payload, _run_folder = self.run_downstream(
            protocol.STAGE_RANK,
            parameters,
            context,
            feedback,
            metric=metric,
            ascending=self.parameterAsBoolean(parameters, self.ASCENDING, context),
            limit=self.parameterAsInt(parameters, self.LIMIT, context),
        )
        rows = payload.get("meta", {}).get("rows", [])
        if rows:
            feedback.pushInfo(self.tr("Top zones by {}:").format(metric))
            for name, value in rows:
                feedback.pushInfo(f"  {name:<28} {value:+.5f}")
        return {self.CSV: payload.get("artifacts", {}).get("csv")}
