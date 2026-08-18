"""AlphaEarth change detection over an extent (AOI + two years).

Draw an extent, pick two years, hit Run. ScruTech queries Google Earth Engine for the
AlphaEarth annual embeddings and returns the pixels whose 64-D signature changed most
between the two years (server-side cosine distance — a real surface change, not an
atmospheric artefact). **No input data**: only a study area and two years.

Needs the VegeVigie interpreter (has ``earthengine-api``) and a GEE service-account
credential stored in QGIS ▸ Authentication under an ID (default ``gee_service``), config
key ``json_credentials``. The credential is read here and passed to the external
interpreter via an environment variable — never written to disk.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterExtent,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


class AlphaEarthChangeAlgorithm(QgsProcessingAlgorithm):
    """Year-over-year AlphaEarth change over an extent (GEE cosine distance)."""

    EXTENT = "EXTENT"
    YEAR1 = "YEAR1"
    YEAR2 = "YEAR2"
    PERCENTILE = "PERCENTILE"
    MAX_PIXELS = "MAX_PIXELS"
    KEY_FILE = "KEY_FILE"
    AUTH_ID = "AUTH_ID"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "alphaearth_change"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("② Changement satellite (AlphaEarth)")

    def group(self) -> str:
        return self.tr("2 · Indicateurs par emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Detect where the AlphaEarth satellite embedding changed between two years over "
            "the extent — a real surface change, computed as a server-side cosine distance on "
            "Google Earth Engine. No input layers: just an area and two years.\n\n"
            "Requires the VegeVigie interpreter (earthengine-api) and a GEE service-account "
            "credential in QGIS ▸ Authentication (config key 'json_credentials')."
        )

    def createInstance(self) -> AlphaEarthChangeAlgorithm:  # noqa: N802
        return AlphaEarthChangeAlgorithm()

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
                self.YEAR1,
                self.tr("Year 1"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2018,
                minValue=2017,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.YEAR2,
                self.tr("Year 2"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=2023,
                minValue=2017,
                maxValue=2100,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.PERCENTILE,
                self.tr("Change percentile threshold"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=95.0,
                minValue=50.0,
                maxValue=99.9,
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.MAX_PIXELS,
                self.tr("Max pixels to sample (GEE quota guard-rail)"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=100_000,
                minValue=1000,
                maxValue=1_000_000,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.KEY_FILE,
                self.tr("GEE service-account key (.json) — empty = SCRUTECH_GEE_CREDENTIALS env"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
                extension="json",
            )
        )
        self.addParameter(
            QgsProcessingParameterString(
                self.AUTH_ID,
                self.tr("GEE auth config ID (fallback — QGIS Authentication)"),
                defaultValue="gee_service",
                optional=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the VegeVigie stack (auto-detected if empty)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
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
        year1 = self.parameterAsInt(parameters, self.YEAR1, context)
        year2 = self.parameterAsInt(parameters, self.YEAR2, context)
        if year1 == year2:
            raise QgsProcessingException(self.tr("Pick two different years."))
        percentile = self.parameterAsDouble(parameters, self.PERCENTILE, context)
        max_pixels = self.parameterAsInt(parameters, self.MAX_PIXELS, context)
        auth_id = self.parameterAsString(parameters, self.AUTH_ID, context).strip()
        key_file = self.parameterAsString(parameters, self.KEY_FILE, context).strip()
        out_folder = self._resolve_output_folder(parameters, context)

        credentials = self._read_credentials(key_file, auth_id)
        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr(
                    "No VegeVigie interpreter found (needs earthengine-api). Point 'Python "
                    "executable' at the project venv."
                )
            )

        from ._external import run_spec

        spec = {
            "task": "alphaearth_change",
            "bbox": list(bbox),
            "year1": year1,
            "year2": year2,
            "percentile": percentile,
            "max_pixels": max_pixels,
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(
                python_exe,
                "vegevigie.qgis_runner",
                spec,
                out_folder,
                feedback,
                extra_env={"SCRUTECH_GEE_CREDENTIALS": credentials},
            )
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        feedback.pushInfo(
            f"Change {year1}→{year2}: {payload.get('n_changed', 0)}/{payload.get('n_pixels', 0)} "
            f"pixels above p{percentile:.0f} (threshold {payload.get('threshold')})."
        )
        self._queue_layers(payload, context, year1, year2)
        return {"CHANGED": payload.get("changed_path"), "ALL": payload.get("geojson_path")}

    # --- helpers -------------------------------------------------------------
    def _read_credentials(self, key_file: str, auth_id: str) -> str:
        """Service-account JSON (compacted to one line), tried: key file → env → QgsAuthManager."""
        import json
        import os

        raw = None
        if key_file:
            path = Path(key_file)
            if not path.exists():
                raise QgsProcessingException(self.tr("GEE key file not found: {}").format(key_file))
            raw = path.read_text(encoding="utf-8")
        elif os.environ.get("SCRUTECH_GEE_CREDENTIALS"):
            raw = os.environ["SCRUTECH_GEE_CREDENTIALS"]
        else:
            config = QgsApplication.authManager().authMethodConfig(auth_id) if auth_id else None
            raw = config.configMap().get("json_credentials") if config else None
        if not raw:
            raise QgsProcessingException(
                self.tr(
                    "No GEE credential. Set the key file (.json) parameter, or the "
                    "SCRUTECH_GEE_CREDENTIALS env var, or store the service-account JSON under "
                    "the 'json_credentials' key of QGIS auth entry '{}'."
                ).format(auth_id or "gee_service")
            )
        try:  # compact to a single line so it crosses the subprocess env safely
            return json.dumps(json.loads(raw))
        except json.JSONDecodeError as exc:
            msg = self.tr("GEE credential is not valid JSON: {}").format(exc)
            raise QgsProcessingException(msg) from exc

    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_alphaearth"
        return Path(value)

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"VegeVigie interpreter: {python_exe}")
        return python_exe

    def _queue_layers(self, payload: dict, context, year1: int, year2: int) -> None:
        pairs = [
            (payload.get("geojson_path"), f"AlphaEarth change {year1}→{year2} (tous pixels)"),
            (payload.get("changed_path"), f"AlphaEarth change {year1}→{year2} (candidats)"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
