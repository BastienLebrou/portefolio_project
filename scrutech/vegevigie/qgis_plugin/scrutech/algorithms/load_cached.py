"""Load a previously computed ScruTech analysis for an AOI — no recompute.

ScruTech caches every AOI run's outputs in the central store keyed by the area's id. This
algorithm resolves the extent to that id and loads the cached layers straight into the
project — instant, offline, the "QGIS reads, the backend computed earlier" promise. Draw the
same extent you analysed before and Run.
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
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


class LoadCachedAlgorithm(QgsProcessingAlgorithm):
    """Load cached ScruTech products for an extent (no recomputation)."""

    EXTENT = "EXTENT"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "load_cached"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("② Recharger une analyse (cache)")

    def group(self) -> str:
        return self.tr("4 · Restituer")

    def groupId(self) -> str:  # noqa: N802
        return "restituer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Load the products ScruTech already computed for this extent from the central "
            "store — no recomputation, no internet. Draw the same extent you analysed and "
            "Run; every cached layer (biotrame, écobuage, VegeVigie, PAF, AlphaEarth) loads "
            "with its style. Needs the VegeVigie interpreter (to resolve the AOI id)."
        )

    def createInstance(self) -> LoadCachedAlgorithm:  # noqa: N802
        return LoadCachedAlgorithm()

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
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the VegeVigie stack (auto-detected if empty)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
                optional=True,
            )
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

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr("No VegeVigie interpreter found. Point 'Python executable' at the venv.")
            )

        from ._external import run_spec

        spec = {"task": "load_cached", "bbox": list(bbox)}
        # The listing is quick; reuse the same output-folder plumbing for the spec file.
        import tempfile

        out_folder = Path(tempfile.gettempdir()) / "scrutech_load"
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        paths = payload.get("paths", [])
        if not paths:
            feedback.reportError(
                self.tr(
                    "Nothing cached for this extent (aoi={}). Run an analysis first, or check "
                    "the extent matches a previous run."
                ).format(payload.get("aoi_id"))
            )
            return {"LOADED": 0}

        feedback.pushInfo(f"Loading {len(paths)} cached layer(s) for aoi={payload.get('aoi_id')}.")
        self._queue_layers(paths, context)
        return {"LOADED": len(paths), "AOI": payload.get("aoi_id")}

    # --- helpers -------------------------------------------------------------
    def _queue_layers(self, paths: list, context: QgsProcessingContext) -> None:
        for path in paths:
            # store layout: {root}/{pilier}/aoi={id}/output/{file} → pilier at parents[2].
            pilier = Path(path).parents[2].name
            label = f"ScruTech (cache) — {pilier} · {Path(path).stem}"
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"VegeVigie interpreter: {python_exe}")
        return python_exe
