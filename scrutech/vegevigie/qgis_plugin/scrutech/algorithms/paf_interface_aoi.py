"""AOI-only PAF algorithm: forest↔built-up interface from a study area alone.

Draw an extent, set the contact distance (default 50 m = OLD débroussaillement), hit
Run. ScruTech fetches the forest (BD TOPO wooded zones) and buildings from the IGN
Géoplateforme for that emprise and computes the Wildland-Urban Interface — **no input
layer required**.

Needs the VegeVigie stack + internet (BD TOPO WFS), so it runs in the external
interpreter (auto-detected, same as ``analyze_extent``).
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
    QgsProcessingParameterNumber,
    QgsProcessingUtils,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


# Même patron QGIS Processing que analyze_extent.py (voir ses commentaires pour le
# détail de initAlgorithm/processAlgorithm/feedback) : ici on délègue systématiquement
# le calcul à l'interpréteur externe via run_spec() (dans _external.py), qui relance
# vegevigie.qgis_runner en sous-processus et relit son flux PROGRESS/RESULT.
class InterfaceFromAoiAlgorithm(QgsProcessingAlgorithm):
    """Wildland-Urban Interface derived from an extent only (BD TOPO forest + buildings)."""

    EXTENT = "EXTENT"
    CONTACT_M = "CONTACT_M"
    PYTHON_EXE = "PYTHON_EXE"
    OUTPUT_FOLDER = "OUTPUT_FOLDER"

    def name(self) -> str:
        return "paf_interface_aoi"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("③ Interface habitat-forêt — feu (PAF)")

    def group(self) -> str:
        return self.tr("2 · Indicateurs par emprise")

    def groupId(self) -> str:  # noqa: N802
        return "indicateurs"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Compute the forest↔built-up interface (WUI) from a study area ALONE: forest "
            "(BD TOPO wooded zones) and buildings are fetched from the IGN Géoplateforme "
            "WFS for the extent — no input layers needed. Produces the frontier line and "
            "the contact band (OLD débroussaillement zone). Needs internet + the VegeVigie "
            "interpreter (auto-detected)."
        )

    def createInstance(self) -> InterfaceFromAoiAlgorithm:  # noqa: N802
        return InterfaceFromAoiAlgorithm()

    def icon(self):  # noqa: N802
        from ._icons import algo_icon

        return algo_icon("paf")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterExtent(self.EXTENT, self.tr("Area of interest (extent)"))
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.CONTACT_M,
                self.tr("Contact distance (m) — OLD débroussaillement = 50"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=50.0,
                minValue=0.0,
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
        from qgis.core import QgsProcessingParameterFolderDestination

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
        contact_m = self.parameterAsDouble(parameters, self.CONTACT_M, context)
        out_folder = self._resolve_output_folder(parameters, context)

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr(
                    "No VegeVigie interpreter found. This algorithm needs GeoPandas + "
                    "requests (BD TOPO fetch), which QGIS's Python usually lacks. Point "
                    "'Python executable' at the project venv."
                )
            )

        from ._external import run_spec

        spec = {
            "task": "paf_interface_aoi",
            "bbox": list(bbox),
            "contact_m": contact_m,
            "out_folder": str(out_folder),
        }
        try:
            payload = run_spec(python_exe, "vegevigie.qgis_runner", spec, out_folder, feedback)
        except RuntimeError as exc:
            raise QgsProcessingException(str(exc)) from exc

        length_km = float(payload.get("interface_length_m", 0.0)) / 1000.0
        band_ha = float(payload.get("interface_zone_ha", 0.0))
        feedback.pushInfo(f"WUI: {length_km:.2f} km of frontier | {band_ha:.1f} ha contact band")
        if length_km == 0:
            feedback.reportError(
                self.tr("No interface found (forest and buildings never within contact distance).")
            )

        self._queue_layers(payload, context)
        return {"LINE": payload.get("line_path"), "ZONE": payload.get("zone_path")}

    # --- helpers -------------------------------------------------------------
    def _resolve_output_folder(self, parameters, context) -> Path:
        value = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)
        if not value or value == "TEMPORARY_OUTPUT":
            return Path(QgsProcessingUtils.tempFolder()) / "scrutech_paf"
        return Path(value)

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]  # scrutech/vegevigie in the dev layout
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"VegeVigie interpreter: {python_exe}")
        return python_exe

    def _queue_layers(self, payload: dict, context: QgsProcessingContext) -> None:
        pairs = [
            (payload.get("line_path"), "PAF interface — frontière"),
            (payload.get("zone_path"), "PAF interface — bande OLD"),
        ]
        for path, label in pairs:
            if not path:
                continue
            details = QgsProcessingContext.LayerDetails(label, context.project(), label)
            context.addLayerToLoadOnCompletion(str(path), details)
