"""One-click algorithm: analyze vegetation trend & drought over an extent.

Draw or pick an extent, set the year window, hit Run — ScruTech searches
Sentinel-2, builds the datacube, and produces greening/browning + drought layers,
loading them straight into the project. Everything heavy runs through the shared
``vegevigie`` engine (the same stages exposed one-by-one under *Pipeline stages*),
and the run folder it leaves behind can be fed to those per-stage algorithms —
e.g. re-rank zones or force just the trend stage without re-downloading.

Because QGIS's bundled Python usually lacks the datacube stack (and installing
rasterio/GDAL into it can clash with QGIS's own GDAL), the engine runs in an
**external interpreter** when the *Python executable* parameter points at a venv
with ``vegevigie`` installed (remembered across sessions). If left empty it runs
in-process, which needs the stack inside QGIS Python.
"""

from __future__ import annotations

from qgis.core import (
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingOutputFile,
    QgsProcessingOutputNumber,
    QgsProcessingOutputRasterLayer,
    QgsProcessingOutputVectorLayer,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterNumber,
)

from .. import protocol
from .base import ScruTechAlgorithmBase


class AnalyzeExtentAlgorithm(ScruTechAlgorithmBase):
    """Full VegeVigie pipeline over a user-drawn extent, in one run."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    MAX_CLOUD = "MAX_CLOUD"
    ZONES = "ZONES"
    TREND = "TREND"
    TREND_CLASS = "TREND_CLASS"
    PVALUE = "PVALUE"
    DROUGHT = "DROUGHT"
    MIN_VCI = "MIN_VCI"
    ZONAL = "ZONAL"
    ZONAL_PARQUET = "ZONAL_PARQUET"
    DUCKDB = "DUCKDB"
    TIMELINE = "TIMELINE"
    SCENES = "SCENES"

    # --- boilerplate identity ------------------------------------------------
    def name(self) -> str:
        return "analyze_extent"

    def displayName(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr("Analyze extent (vegetation trend & drought)")

    def group(self) -> str:
        return self.tr("Analysis")

    def groupId(self) -> str:  # noqa: N802 — QGIS API name
        return "analysis"

    def shortHelpString(self) -> str:  # noqa: N802 — QGIS API name
        return self.tr(
            "Search Sentinel-2 over the extent, build monthly NDVI composites, and "
            "compute per-pixel greening/browning trend (Mann-Kendall + Sen's slope) and "
            "NDVI-anomaly drought stress. Optionally aggregate to a zones layer. "
            "Outputs are written to the run folder and loaded into the project; the "
            "folder can then feed the per-stage algorithms (re-rank, force one stage…).\n\n"
            "Needs internet access to Microsoft Planetary Computer. Set 'Python "
            "executable' to a venv that has the VegeVigie stack (recommended); leave it "
            "empty to run inside QGIS's Python (requires the stack installed there)."
        )

    # --- parameters ----------------------------------------------------------
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
                self.tr("Resolution (m)"),
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
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.ZONES,
                self.tr("Zones for aggregation (optional, e.g. communes)"),
                optional=True,
            )
        )
        self.add_python_parameter()
        self.add_force_parameter()
        self.add_output_folder_parameter()

        self.addOutput(QgsProcessingOutputRasterLayer(self.TREND, self.tr("Trend — Sen's slope")))
        self.addOutput(QgsProcessingOutputRasterLayer(self.TREND_CLASS, self.tr("Trend — class")))
        self.addOutput(QgsProcessingOutputRasterLayer(self.PVALUE, self.tr("Trend — p-value")))
        self.addOutput(
            QgsProcessingOutputRasterLayer(self.DROUGHT, self.tr("Drought — mean anomaly"))
        )
        self.addOutput(
            QgsProcessingOutputRasterLayer(self.MIN_VCI, self.tr("Drought — minimum VCI"))
        )
        self.addOutput(QgsProcessingOutputVectorLayer(self.ZONAL, self.tr("Zone statistics")))
        self.addOutput(
            QgsProcessingOutputFile(self.ZONAL_PARQUET, self.tr("Zone statistics (GeoParquet)"))
        )
        self.addOutput(QgsProcessingOutputFile(self.DUCKDB, self.tr("DuckDB store")))
        self.addOutput(
            QgsProcessingOutputFile(self.TIMELINE, self.tr("Drought timeline (parquet)"))
        )
        self.addOutput(QgsProcessingOutputNumber(self.SCENES, self.tr("Scenes used")))

    # --- run -----------------------------------------------------------------
    def processAlgorithm(  # noqa: N802 — QGIS API name
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        bbox = self.extent_to_bbox(parameters, self.EXTENT, context)
        out_folder = self.resolve_output_folder(parameters, context)
        python_exe = self.resolve_python(parameters, context)
        zones_path = self.zones_to_gpkg(parameters, self.ZONES, context, out_folder, feedback)

        spec = protocol.build_spec(
            protocol.STAGE_ALL,
            str(out_folder),
            bbox=bbox,
            start=self.parameterAsInt(parameters, self.START_YEAR, context),
            end=self.parameterAsInt(parameters, self.END_YEAR, context),
            resolution=self.parameterAsInt(parameters, self.RESOLUTION, context),
            max_cloud=self.parameterAsInt(parameters, self.MAX_CLOUD, context),
            zones_path=str(zones_path) if zones_path else None,
            force=self.parameterAsBoolean(parameters, self.FORCE, context),
        )
        payload = self.run_spec(spec, python_exe, out_folder, feedback)

        if int(payload.get("scene_count", 0)) == 0:
            feedback.reportError(self.tr("No Sentinel-2 scenes found for this AOI/window."))

        self.queue_layer(
            context, payload.get("trend_tif"), "ScruTech trend (Sen's slope)", "trend_sen_slope"
        )
        self.queue_layer(
            context, payload.get("trend_class_tif"), "ScruTech trend class", "trend_class"
        )
        self.queue_layer(
            context,
            payload.get("drought_tif"),
            "ScruTech drought (NDVI anomaly)",
            "drought_anomaly",
        )
        self.queue_layer(
            context, payload.get("vci_tif"), "ScruTech drought (min VCI)", "drought_vci"
        )
        self.queue_layer(context, payload.get("zonal_gpkg"), "ScruTech zone stats", "zonal_stats")

        return {
            self.OUTPUT_FOLDER: str(out_folder),
            self.TREND: payload.get("trend_tif"),
            self.TREND_CLASS: payload.get("trend_class_tif"),
            self.PVALUE: payload.get("pvalue_tif"),
            self.DROUGHT: payload.get("drought_tif"),
            self.MIN_VCI: payload.get("vci_tif"),
            self.ZONAL: payload.get("zonal_gpkg"),
            self.ZONAL_PARQUET: payload.get("zonal_parquet"),
            self.DUCKDB: payload.get("duckdb"),
            self.TIMELINE: payload.get("timeline_parquet"),
            self.SCENES: int(payload.get("scene_count", 0)),
        }
