"""One-click algorithm: analyze vegetation trend & drought over an extent.

Draw or pick an extent, set the year window, hit Run — ScruTech searches
Sentinel-2, builds the datacube, and produces greening/browning + drought layers,
loading them straight into the project. Everything heavy runs through the shared
:mod:`vegevigie.pipeline` engine.

Because QGIS's bundled Python usually lacks the datacube stack (and installing
rasterio/GDAL into it can clash with QGIS's own GDAL), the algorithm can run the
engine in an **external interpreter** — point the *Python executable* parameter at
a venv that has ``vegevigie`` installed (e.g. the project's ``uv`` venv). If that
field is left empty it runs in-process, which needs the stack inside QGIS Python.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat

# QGIS sets these to point at its own runtime; they must NOT leak into an external
# Python interpreter or they break its rasterio/pyproj/GDAL.
_ENV_STRIP = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "GDAL_DATA",
    "GDAL_DRIVER_PATH",
    "PROJ_LIB",
    "PROJ_DATA",
    "GEOTIFF_CSV",
)


class AnalyzeExtentAlgorithm(QgsProcessingAlgorithm):
    """Full VegeVigie pipeline over a user-drawn extent, in one run."""

    EXTENT = "EXTENT"
    START_YEAR = "START_YEAR"
    END_YEAR = "END_YEAR"
    RESOLUTION = "RESOLUTION"
    MAX_CLOUD = "MAX_CLOUD"
    ZONES = "ZONES"
    PYTHON_EXE = "PYTHON_EXE"
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
            "Needs internet access to Microsoft Planetary Computer. Set 'Python "
            "executable' to a venv that has the VegeVigie stack (recommended); leave it "
            "empty to run inside QGIS's Python (requires the stack installed there)."
        )

    def createInstance(self) -> AnalyzeExtentAlgorithm:  # noqa: N802
        return AnalyzeExtentAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("vegevigie")

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
                type=_compat.NUMBER_INTEGER,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.END_YEAR,
                self.tr("End year"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2020,
                minValue=2015,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.RESOLUTION,
                self.tr("Resolution (m)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=60,
                minValue=10,
                maxValue=200,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_CLOUD,
                self.tr("Max scene cloud cover (%)"),
                type=_compat.NUMBER_INTEGER,
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
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the VegeVigie stack (recommended)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
            )
        )
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
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(self.tr("The extent is empty."))
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())

        start = self.parameterAsInt(parameters, self.START_YEAR, context)
        end = self.parameterAsInt(parameters, self.END_YEAR, context)
        resolution = self.parameterAsInt(parameters, self.RESOLUTION, context)
        max_cloud = self.parameterAsInt(parameters, self.MAX_CLOUD, context)
        out_folder = self._resolve_output_folder(parameters, context)
        python_exe = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        zones_path = self._zones_to_path(parameters, context, out_folder, feedback)

        if python_exe:
            result = self._run_external(
                python_exe,
                bbox,
                start,
                end,
                resolution,
                max_cloud,
                out_folder,
                zones_path,
                feedback,
            )
        else:
            result = self._run_in_process(
                bbox,
                start,
                end,
                resolution,
                max_cloud,
                out_folder,
                zones_path,
                feedback,
            )

        if result.scene_count == 0:
            feedback.reportError(self.tr("No Sentinel-2 scenes found for this AOI/window."))
        self._queue_layers(result, context)
        return {
            "TREND": _s(result.trend_tif),
            "DROUGHT": _s(result.drought_tif),
            "ZONAL": _s(result.zonal_parquet),
            "SCENES": result.scene_count,
        }

    # --- execution modes -----------------------------------------------------
    def _run_in_process(
        self, bbox, start, end, resolution, max_cloud, out_folder, zones_path, feedback
    ) -> SimpleNamespace:
        from ..dependencies import install_hint, missing_dependencies

        missing = missing_dependencies()
        if missing:
            raise QgsProcessingException(install_hint(missing))

        from vegevigie.pipeline import build_settings, run_pipeline

        settings = build_settings(
            bbox,
            start,
            end,
            resolution=resolution,
            max_cloud_cover=max_cloud,
            data_dir=out_folder,
            base=self._load_base_settings(),
        )
        zones_gdf = None
        if zones_path is not None:
            import geopandas as gpd

            zones_gdf = gpd.read_file(zones_path)

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
        return SimpleNamespace(
            trend_tif=result.trend_tif,
            drought_tif=result.drought_tif,
            zonal_parquet=result.zonal_parquet,
            scene_count=result.scene_count,
        )

    def _run_external(
        self,
        python_exe,
        bbox,
        start,
        end,
        resolution,
        max_cloud,
        out_folder,
        zones_path,
        feedback,
    ) -> SimpleNamespace:
        out_folder.mkdir(parents=True, exist_ok=True)
        spec = {
            "bbox": list(bbox),
            "start": start,
            "end": end,
            "resolution": resolution,
            "max_cloud": max_cloud,
            "out_folder": str(out_folder),
            "zones_path": str(zones_path) if zones_path else None,
        }
        spec_path = out_folder / "scrutech_spec.json"
        spec_path.write_text(json.dumps(spec))

        cmd = [python_exe, "-m", "vegevigie.qgis_runner", str(spec_path)]
        feedback.pushInfo("Running engine in external interpreter:\n  " + " ".join(cmd))

        env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            creationflags=creationflags,
        )
        payload: dict = {}
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if feedback.isCanceled():
                proc.terminate()
                raise QgsProcessingException(self.tr("Canceled."))
            if line.startswith("PROGRESS "):
                _, _, rest = line.partition(" ")
                pct, _, msg = rest.partition(" ")
                with contextlib.suppress(ValueError):
                    feedback.setProgress(int(pct))
                feedback.pushInfo(msg)
            elif line.startswith("RESULT "):
                payload = json.loads(line[len("RESULT ") :])
            elif line:
                feedback.pushInfo(line)
        proc.wait()

        if payload.get("error"):
            raise QgsProcessingException(self._explain_text(payload["error"]))
        if proc.returncode != 0 and not payload:
            raise QgsProcessingException(
                self.tr("External interpreter failed (exit {}). Check the log above.").format(
                    proc.returncode
                )
            )
        return SimpleNamespace(
            trend_tif=_p(payload.get("trend_tif")),
            drought_tif=_p(payload.get("drought_tif")),
            zonal_parquet=_p(payload.get("zonal_parquet")),
            scene_count=int(payload.get("scene_count", 0)),
        )

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech"
        return Path(value)

    def _load_base_settings(self):
        from vegevigie.config import load_settings

        bundled = Path(__file__).resolve().parents[1] / "config" / "default.yaml"
        return load_settings(bundled) if bundled.exists() else load_settings()

    def _zones_to_path(self, parameters, context, out_folder, feedback) -> Path | None:
        layer = self.parameterAsVectorLayer(parameters, self.ZONES, context)
        if layer is None:
            return None
        from qgis.core import QgsVectorFileWriter

        out_folder.mkdir(parents=True, exist_ok=True)
        tmp = out_folder / "scrutech_zones.gpkg"
        QgsVectorFileWriter.writeAsVectorFormat(layer, str(tmp), "utf-8", layer.crs(), "GPKG")
        feedback.pushInfo(f"Prepared zones layer ({layer.featureCount()} features).")
        return tmp

    def _queue_layers(self, result, context: QgsProcessingContext) -> None:
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
        return AnalyzeExtentAlgorithm._explain_text(str(exc))

    @staticmethod
    def _explain_text(text: str) -> str:
        if any(m in text for m in ("403", "Forbidden", "Proxy", "Max retries")):
            return (
                "Could not reach Microsoft Planetary Computer "
                "(planetarycomputer.microsoft.com). Check internet access / proxy / "
                "firewall and retry.\n\nOriginal error: " + text
            )
        return "Pipeline failed: " + text


def _s(path) -> str | None:
    return str(path) if path else None


def _p(value) -> Path | None:
    return Path(value) if value else None
