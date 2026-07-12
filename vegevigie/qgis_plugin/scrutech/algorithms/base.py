"""Shared machinery for every ScruTech Processing algorithm.

One base class owns everything the algorithms have in common — the *Python
executable* parameter (persisted in ``QgsSettings`` so it's typed once, with a
sensible auto-detected default), output/run-folder handling, the external
interpreter subprocess with its line protocol (progress, heartbeat,
cancellation), the in-process fallback, error explanation and styled layer
loading. Concrete algorithms shrink to parameter declarations + a spec
(qgis_plugin/ROADMAP.md §4). Both execution modes return the exact same payload
shape, assembled by ``vegevigie.qgis_runner``.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingLayerPostProcessorInterface,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterDefinition,
    QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination,
    QgsProcessingUtils,
    QgsSettings,
)
from qgis.PyQt.QtCore import QCoreApplication

from .. import protocol

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

# QgsSettings key remembering the last interpreter the user pointed ScruTech at.
SETTINGS_KEY_PYTHON = "scrutech/python_exe"

_STYLE_DIR = Path(__file__).resolve().parents[1] / "styles"


class _StyleAttacher(QgsProcessingLayerPostProcessorInterface):
    """Apply a bundled QML once the layer lands in the project.

    QGIS holds only a weak reference to post-processors, so instances park
    themselves in ``_KEEP`` to survive until they run.
    """

    _KEEP: list[_StyleAttacher] = []

    def __init__(self, qml_path: Path) -> None:
        super().__init__()
        self._qml = qml_path
        _StyleAttacher._KEEP.append(self)

    def postProcessLayer(self, layer, context, feedback) -> None:  # noqa: N802 — QGIS API
        layer.loadNamedStyle(str(self._qml))
        layer.triggerRepaint()


class ScruTechAlgorithmBase(QgsProcessingAlgorithm):
    """Base class: common parameters + one engine-call path for all algorithms."""

    PYTHON_EXE = "PYTHON_EXE"
    RUN_FOLDER = "RUN_FOLDER"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"
    FORCE = "FORCE"

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def createInstance(self) -> ScruTechAlgorithmBase:  # noqa: N802 — QGIS API name
        return type(self)()

    # --- shared parameters ----------------------------------------------------
    def add_python_parameter(self) -> None:
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the VegeVigie stack (empty = QGIS Python)"),
                behavior=QgsProcessingParameterFile.File,
                optional=True,
                defaultValue=self.default_python() or None,
            )
        )

    def add_output_folder_parameter(self) -> None:
        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER, self.tr("Run folder (outputs land here)")
            )
        )

    def add_run_folder_parameter(self) -> None:
        self.addParameter(
            QgsProcessingParameterFile(
                self.RUN_FOLDER,
                self.tr("Run folder (from 'Search scenes' or 'Analyze extent')"),
                behavior=QgsProcessingParameterFile.Folder,
            )
        )

    def add_force_parameter(self) -> None:
        param = QgsProcessingParameterBoolean(
            self.FORCE,
            self.tr("Force recompute (ignore cached stage outputs)"),
            defaultValue=False,
        )
        param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
        self.addParameter(param)

    def init_downstream_parameters(self) -> None:
        """The parameter trio every post-search stage shares."""
        self.add_run_folder_parameter()
        self.add_python_parameter()
        self.add_force_parameter()

    def default_python(self) -> str:
        """Best-effort interpreter default: QgsSettings > env var > repo venv."""
        stored = str(QgsSettings().value(SETTINGS_KEY_PYTHON, "") or "")
        if stored and Path(stored).exists():
            return stored
        env = os.environ.get("VEGEVIGIE_PYTHON", "")
        if env and Path(env).exists():
            return env
        # Dev layout: <repo>/vegevigie/qgis_plugin/scrutech/algorithms/base.py
        repo_venv = Path(__file__).resolve().parents[3] / ".venv"
        for candidate in (repo_venv / "bin" / "python", repo_venv / "Scripts" / "python.exe"):
            if candidate.exists():
                return str(candidate)
        return ""

    def resolve_python(self, parameters: dict, context: QgsProcessingContext) -> str:
        """Read the interpreter parameter and remember it for the next dialog."""
        exe = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        if exe:
            QgsSettings().setValue(SETTINGS_KEY_PYTHON, exe)
        return exe

    def resolve_output_folder(self, parameters: dict, context: QgsProcessingContext) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech"
        return Path(value)

    def resolve_run_folder(self, parameters: dict, context: QgsProcessingContext) -> Path:
        return Path(self.parameterAsString(parameters, self.RUN_FOLDER, context))

    def extent_to_bbox(
        self, parameters: dict, name: str, context: QgsProcessingContext
    ) -> tuple[float, float, float, float]:
        """Extent parameter -> WGS84 (min_lon, min_lat, max_lon, max_lat)."""
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, name, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(self.tr("The extent is empty."))
        return (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())

    def zones_to_gpkg(
        self,
        parameters: dict,
        name: str,
        context: QgsProcessingContext,
        out_folder: Path,
        feedback: QgsProcessingFeedback,
    ) -> Path | None:
        """Export an optional zones layer to a GPKG the engine can read."""
        layer = self.parameterAsVectorLayer(parameters, name, context)
        if layer is None:
            return None
        from qgis.core import QgsVectorFileWriter

        out_folder.mkdir(parents=True, exist_ok=True)
        target = out_folder / "scrutech_zones.gpkg"
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.fileEncoding = "utf-8"
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer, str(target), context.transformContext(), options
        )
        if error[0] != QgsVectorFileWriter.NoError:
            raise QgsProcessingException(
                self.tr("Could not export the zones layer: {}").format(error[1])
            )
        feedback.pushInfo(f"Prepared zones layer ({layer.featureCount()} features).")
        return target

    # --- engine execution -------------------------------------------------------
    def run_spec(
        self,
        spec: dict,
        python_exe: str,
        out_folder: Path,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        """Run one engine spec — externally when an interpreter is set, else in-process.

        Returns the runner payload; raises ``QgsProcessingException`` on failure.
        """
        if python_exe:
            return self._run_external(spec, python_exe, out_folder, feedback)
        return self._run_in_process(spec, feedback)

    def run_downstream(
        self,
        stage: str,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
        **extra: object,
    ) -> tuple[dict, Path]:
        """Run a post-search stage against a run folder; returns (payload, folder)."""
        run_folder = self.resolve_run_folder(parameters, context)
        python_exe = self.resolve_python(parameters, context)
        spec = protocol.build_spec(
            stage,
            str(run_folder),
            force=self.parameterAsBoolean(parameters, self.FORCE, context),
            **extra,
        )
        payload = self.run_spec(spec, python_exe, run_folder, feedback)
        if payload.get("skipped"):
            feedback.pushInfo(self.tr("Stage was up to date — reused cached outputs."))
        return payload, run_folder

    def _run_in_process(self, spec: dict, feedback: QgsProcessingFeedback) -> dict:
        from ..dependencies import install_hint, missing_dependencies

        missing = missing_dependencies()
        if missing:
            raise QgsProcessingException(install_hint(missing))

        from vegevigie import qgis_runner

        def report(pct: int, msg: str) -> None:
            if feedback.isCanceled():
                raise QgsProcessingException(self.tr("Canceled."))
            feedback.setProgress(pct)
            feedback.pushInfo(msg)

        stage = spec.get("stage", protocol.STAGE_ALL)
        try:
            settings = qgis_runner.settings_for_spec(spec)
            if stage == protocol.STAGE_ALL:
                return qgis_runner.run_all_payload(spec, settings, progress=report)
            return qgis_runner.run_stage_payload(spec, settings, stage, progress=report)
        except QgsProcessingException:
            raise
        except Exception as exc:  # noqa: BLE001 — engine errors become readable messages
            raise QgsProcessingException(protocol.explain_error(str(exc))) from exc

    def _run_external(
        self,
        spec: dict,
        python_exe: str,
        out_folder: Path,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        out_folder.mkdir(parents=True, exist_ok=True)
        stage = spec.get("stage", protocol.STAGE_ALL)
        spec_path = out_folder / f"scrutech_spec_{stage}.json"
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
            if feedback.isCanceled():
                proc.terminate()
                try:
                    proc.wait(3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise QgsProcessingException(self.tr("Canceled."))
            line = protocol.parse_line(raw)
            if line.kind == "heartbeat":
                continue  # only exists to wake this loop for the cancel check
            if line.kind == "progress":
                feedback.setProgress(line.percent or 0)
                feedback.pushInfo(line.message)
            elif line.kind == "result":
                payload = line.payload or {}
            elif line.message:
                feedback.pushInfo(line.message)
        proc.wait()

        if payload.get("error"):
            raise QgsProcessingException(protocol.explain_error(payload["error"]))
        if proc.returncode != 0 and not payload:
            raise QgsProcessingException(
                self.tr("External interpreter failed (exit {}). Check the log above.").format(
                    proc.returncode
                )
            )
        return payload

    # --- results ---------------------------------------------------------------
    def queue_layer(
        self,
        context: QgsProcessingContext,
        path: str | Path | None,
        label: str,
        style: str | None = None,
    ) -> None:
        """Load an output as a project layer, applying a bundled QML if present."""
        if not path:
            return
        details = QgsProcessingContext.LayerDetails(label, context.project(), label)
        if style is not None:
            qml = _STYLE_DIR / f"{style}.qml"
            if qml.exists():
                details.setPostProcessor(_StyleAttacher(qml))
        context.addLayerToLoadOnCompletion(str(path), details)
