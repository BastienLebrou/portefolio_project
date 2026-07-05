"""One-click algorithm: analyze vegetation trend & drought over an extent.

Draw or pick an extent, set the year window, hit Run — ScruTech searches
Sentinel-2, builds the datacube, and produces greening/browning + drought layers,
loading them straight into the project. Everything heavy runs through the shared
:mod:`vegevigie.pipeline` engine.
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
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QCoreApplication


class AnalyzeExtentAlgorithm(QgsProcessingAlgorithm):
    """Full VegeVigie pipeline over a user-drawn extent, in one run."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    MAX_CLOUD = "MAX_CLOUD"
    ZONES = "ZONES"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    # --- boilerplate identity ------------------------------------------------
    def name(self) -> str:
        return "analyze_extent"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Analyze extent (vegetation trend & drought)")

    def group(self) -> str:
        return self.tr("Analysis")

    def groupId(self) -> str:  # noqa: N802
        return "analysis"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Search Sentinel-2 over the extent, build monthly NDVI composites, and "
            "compute per-pixel greening/browning trend (Mann-Kendall + Sen's slope) and "
            "NDVI-anomaly drought stress. Optionally aggregate to a zones layer. "
            "Outputs are written to the chosen folder and loaded into the project.\n\n"
            "Needs internet access to Microsoft Planetary Computer and the VegeVigie "
            "datacube stack installed in QGIS's Python (see the plugin README)."
        )

    def createInstance(self) -> AnalyzeExtentAlgorithm:  # noqa: N802
        return AnalyzeExtentAlgorithm()

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    # --- parameters ----------------------------------------------------------
    def initAlgorithm(self, config=None) -> None:  # noqa: N802
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
        zones = QgsProcessingParameterFeatureSource(
            self.ZONES,
            self.tr("Zones for aggregation (optional, e.g. communes)"),
            optional=True,
        )
        self.addParameter(zones)
        self.addParameter(
            QgsProcessingParameterFolderDestination(self.OUTPUT_FOLDER, self.tr("Output folder"))
        )

    # --- run -----------------------------------------------------------------
    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from ..dependencies import install_hint, missing_dependencies

        missing = missing_dependencies()
        if missing:
            raise QgsProcessingException(install_hint(missing))

        from vegevigie.pipeline import build_settings, run_pipeline

        # Extent -> WGS84 bbox (QGIS reprojects for us).
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        if rect.isEmpty():
            raise QgsProcessingException(self.tr("The extent is empty."))

        start = self.parameterAsInt(parameters, self.START_YEAR, context)
        end = self.parameterAsInt(parameters, self.END_YEAR, context)
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        max_cloud = self.parameterAsInt(parameters, self.MAX_CLOUD, context)
        out_folder = Path(self.parameterAsString(parameters, self.OUTPUT_FOLDER, context))

        base = self._load_base_settings()
        settings = build_settings(
            bbox,
            start,
            end,
            resolution=resolution,
            max_cloud_cover=max_cloud,
            data_dir=out_folder,
            base=base,
        )

        zones_gdf = self._zones_to_geodataframe(parameters, context, feedback)

        def progress(pct: int, msg: str) -> None:
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Canceled."))
            feedback.setProgress(pct)
            feedback.pushInfo(msg)

        try:
            result = run_pipeline(settings, zones=zones_gdf, progress=progress)
        except QgsProcessingException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise QgsProcessingException(self._explain(exc)) from exc

        if result.scene_count == 0:
            feedback.reportError(self.tr("No Sentinel-2 scenes found for this AOI/window."))

        self._queue_layers(result, context)
        return {
            "TREND": str(result.trend_tif) if result.trend_tif else None,
            "DROUGHT": str(result.drought_tif) if result.drought_tif else None,
            "ZONAL": str(result.zonal_parquet) if result.zonal_parquet else None,
            "SCENES": result.scene_count,
        }

    # --- helpers -------------------------------------------------------------
    def _load_base_settings(self):
        from vegevigie.config import load_settings

        bundled = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
        return load_settings(bundled) if bundled.exists() else load_settings()

    def _zones_to_geodataframe(self, parameters, context, feedback):
        source = self.parameterAsSource(parameters, self.ZONES, context)
        if source is None:
            return None
        import geopandas as gpd
        from qgis.core import QgsVectorFileWriter

        tmp = Path(context.temporaryFolder() or ".") / "scrutech_zones.gpkg"
        layer = self.parameterAsVectorLayer(parameters, self.ZONES, context)
        if layer is None:
            return None
        QgsVectorFileWriter.writeAsVectorFormat(layer, str(tmp), "utf-8", layer.crs(), "GPKG")
        gdf = gpd.read_file(tmp)
        feedback.pushInfo(f"Loaded {len(gdf)} zones for aggregation.")
        return gdf

    def _queue_layers(self, result, context: QgsProcessingContext) -> None:
        from qgis.core import QgsProcessingContext

        pairs = [
            (result.trend_tif, "ScruTech trend (Sen's slope)"),
            (result.drought_tif, "ScruTech drought (NDVI anomaly)"),
            (result.zonal_parquet, "ScruTech commune stats"),
        ]
        for path, label in pairs:
            if path is None:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)

    @staticmethod
    def _explain(exc: Exception) -> str:
        text = str(exc)
        if "403" in text or "Forbidden" in text or "Proxy" in text or "Max retries" in text:
            return (
                "Could not reach Microsoft Planetary Computer "
                "(planetarycomputer.microsoft.com). Check the machine's internet access / "
                "proxy / firewall and retry.\n\nOriginal error: " + text
            )
        return "Pipeline failed: " + text
