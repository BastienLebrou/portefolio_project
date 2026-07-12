"""Stage 5: aggregate the trend/drought rasters to a zones layer (e.g. communes)."""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingOutputFolder,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterFeatureSource,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class ZonalStatsAlgorithm(ScruTechAlgorithmBase):
    """Per-zone slope, %greening/browning, anomaly and VCI → GPKG + Parquet + DuckDB."""

    ZONES = "ZONES"
    STATS_GPKG = "STATS_GPKG"
    STATS_PARQUET = "STATS_PARQUET"
    DUCKDB = "DUCKDB"
    RUN_FOLDER_OUT = "RUN_FOLDER_OUT"

    def name(self) -> str:
        return "zonal_stats"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("5 — Zonal statistics")

    def group(self) -> str:
        return self.tr("Pipeline stages")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "stages"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Summarize the trend and drought rasters of a run folder per zone polygon "
            "(e.g. communes from 'Load commune boundaries'): mean Sen's slope, "
            "% significantly greening/browning pixels, mean anomaly and worst VCI. "
            "Writes a GeoPackage (loaded), a GeoParquet and a DuckDB table for ranking."
        )

    def initAlgorithm(self, config=None) -> None:  # noqa: N802 — QGIS API name
        self.add_run_folder_parameter()
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ZONES, self.tr("Zones (polygons, e.g. communes)")
            )
        )
        self.add_python_parameter()
        self.add_force_parameter()
        self.addOutput(
            QgsProcessingOutputVectorLayer(self.STATS_GPKG, self.tr("Zone statistics (GPKG)"))
        )
        self.addOutput(
            QgsProcessingOutputFile(self.STATS_PARQUET, self.tr("Zone statistics (GeoParquet)"))
        )
        self.addOutput(QgsProcessingOutputFile(self.DUCKDB, self.tr("DuckDB store")))
        self.addOutput(QgsProcessingOutputFolder(self.RUN_FOLDER_OUT, self.tr("Run folder")))

    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        run_folder = self.resolve_run_folder(parameters, context)
        zones_path = self.zones_to_gpkg(parameters, self.ZONES, context, run_folder, feedback)
        payload, run_folder = self.run_downstream(
            protocol.STAGE_ZONAL,
            parameters,
            context,
            feedback,
            zones_path=str(zones_path) if zones_path else None,
        )
        artifacts = payload.get("artifacts", {})
        self.queue_layer(context, artifacts.get("stats_gpkg"), "ScruTech zone stats", "zonal_stats")
        return {
            self.STATS_GPKG: artifacts.get("stats_gpkg"),
            self.STATS_PARQUET: artifacts.get("stats_parquet"),
            self.DUCKDB: artifacts.get("duckdb"),
            self.RUN_FOLDER_OUT: str(run_folder),
        }
