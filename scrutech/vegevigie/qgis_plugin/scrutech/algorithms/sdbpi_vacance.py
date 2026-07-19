"""SDBPi algorithm: vacant professional buildings (BD TOPO × SIRENE).

Runs the SDBPi pipeline in an external Python (it needs GeoPandas + requests +
network — not QGIS's bundled stack) and loads the vacancy-candidate layer. The
AOI-first signature and output routing to the ScruTech layout/DB land with the core
refactor; for now it drives the tool's ``--insee`` CLI.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterEnum,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsProcessingParameterString,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat

_SOURCES = ["api", "geo_file", "grandlyon"]


class SdbpiVacanceAlgorithm(QgsProcessingAlgorithm):
    """Cross BD TOPO buildings with active SIRENE establishments to flag vacancy."""

    INSEE = "INSEE"
    BUFFER = "BUFFER"
    SOURCE = "SOURCE"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "sdbpi_vacance"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Bâtiments professionnels inoccupés (SDBPi)")

    def group(self) -> str:
        return self.tr("SDBPi")

    def groupId(self) -> str:  # noqa: N802
        return "sdbpi"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Cross BD TOPO commercial/industrial buildings with active geolocated SIRENE "
            "establishments over a commune (INSEE code): a building with none nearby is a "
            "vacancy CANDIDATE (to verify on the ground, not a certainty). Runs in an "
            "external Python that has the SDBPi stack (GeoPandas, requests) — set 'Python "
            "executable' to a venv with it. Needs internet (BD TOPO WFS + SIRENE)."
        )

    def createInstance(self) -> SdbpiVacanceAlgorithm:  # noqa: N802
        return SdbpiVacanceAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("sdbpi")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterString(self.INSEE, self.tr("Code INSEE commune"), "01053")
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.BUFFER,
                self.tr("Buffer (m) — 25-30 recommandé en tissu mixte"),
                type=_compat.NUMBER_DOUBLE,
                defaultValue=15.0,
                minValue=0.0,
            )
        )
        self.addParameter(
            QgsProcessingParameterEnum(
                self.SOURCE, self.tr("Source SIRENE"), options=_SOURCES, defaultValue=0
            )
        )
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the SDBPi stack (geopandas, requests)"),
                behavior=_compat.FILE_BEHAVIOR_FILE,
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from ._external import run_engine

        insee = self.parameterAsString(parameters, self.INSEE, context).strip()
        buffer_m = self.parameterAsDouble(parameters, self.BUFFER, context)
        source = _SOURCES[self.parameterAsEnum(parameters, self.SOURCE, context)]
        python_exe = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        if not python_exe:
            raise QgsProcessingException(
                self.tr("Set 'Python executable' to a venv with geopandas + requests.")
            )

        sdbpi_dir = Path(__file__).resolve().parents[1] / "sdbpi"
        script = sdbpi_dir / "run_vacance.py"
        if not script.exists():
            raise QgsProcessingException(self.tr(f"Bundled SDBPi engine not found: {script}"))

        code = run_engine(
            python_exe,
            script,
            ["--insee", insee, "--buffer", str(buffer_m), "--source", source],
            feedback,
        )
        if code != 0:
            raise QgsProcessingException(self.tr(f"SDBPi engine failed (exit {code}). See log."))

        out_gpkg = sdbpi_dir / "BDD" / "_vacance" / insee / f"batiments_vacance_{insee}.gpkg"
        if not out_gpkg.exists():
            raise QgsProcessingException(self.tr(f"Expected SDBPi output not found: {out_gpkg}"))
        details = QgsProcessingContext.LayerDetails(
            f"SDBPi {insee} — bâtiments inoccupés (candidats)", context.project(), "sdbpi"
        )
        context.addLayerToLoadOnCompletion(str(out_gpkg), details)
        feedback.pushInfo(f"Loaded {out_gpkg}")
        return {"OUTPUT": str(out_gpkg)}
