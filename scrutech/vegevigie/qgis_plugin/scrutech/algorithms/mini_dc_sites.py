"""Mini data centers algorithm: residential site selection (synthetic demo).

Runs the mini_dc pipeline (synthetic Alba dataset → DuckDB-spatial 5-filter scoring)
in an external Python and loads the eligible-parcels + heatmap layers. Running it on a
real AOI (instead of the bundled synthetic commune) lands with the core refactor; for
now it runs the reproducible demo.
"""

from __future__ import annotations

from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingContext,
    QgsProcessingException,
    QgsProcessingFeedback,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterFile,
)
from qgis.PyQt.QtCore import QCoreApplication


class MiniDcSitesAlgorithm(QgsProcessingAlgorithm):
    """Score cadastral parcels for mini-data-center siting (multi-criteria funnel)."""

    NO_GENERATE = "NO_GENERATE"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "mini_dc_sites"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Sélection de sites mini data centers (démo)")

    def group(self) -> str:
        return self.tr("Mini data centers")

    def groupId(self) -> str:  # noqa: N802
        return "mini_dc"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Run the mini-data-center site-selection pipeline: a 5-filter spatial funnel "
            "(land, nuisances, fibre, energy, regulatory) scoring cadastral parcels, on a "
            "reproducible synthetic dataset (commune of Alba-la-Romaine). Loads the "
            "eligible parcels and the H3 heatmap. Runs in an external Python that has the "
            "stack (GeoPandas, DuckDB) — set 'Python executable' to a venv with it."
        )

    def createInstance(self) -> MiniDcSitesAlgorithm:  # noqa: N802
        return MiniDcSitesAlgorithm()

    def icon(self):  # noqa: N802 — QGIS API name
        from ._icons import algo_icon

        return algo_icon("mini_dc")

    def tr(self, string: str) -> str:
        return QCoreApplication.translate("ScruTech", string)

    def initAlgorithm(self, config=None) -> None:  # noqa: N802
        self.addParameter(
            QgsProcessingParameterFile(
                self.PYTHON_EXE,
                self.tr("Python executable with the mini_dc stack (geopandas, duckdb)"),
                behavior=QgsProcessingParameterFile.File,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.NO_GENERATE,
                self.tr("Réutiliser les données synthétiques existantes (--no-generate)"),
                defaultValue=False,
            )
        )

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        from ._external import run_engine

        python_exe = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        if not python_exe:
            raise QgsProcessingException(
                self.tr("Set 'Python executable' to a venv with geopandas + duckdb.")
            )
        no_generate = self.parameterAsBool(parameters, self.NO_GENERATE, context)

        mini_dc_dir = Path(__file__).resolve().parents[1] / "mini_dc"
        script = mini_dc_dir / "run.py"
        if not script.exists():
            raise QgsProcessingException(self.tr(f"Bundled mini_dc engine not found: {script}"))

        args = ["--no-generate"] if no_generate else []
        code = run_engine(python_exe, script, args, feedback)
        if code != 0:
            raise QgsProcessingException(self.tr(f"mini_dc engine failed (exit {code}). See log."))

        out_dir = mini_dc_dir / "data" / "outputs"
        loaded = 0
        for fname, label in (
            ("parcelles_eligibles.geojson", "Mini DC — parcelles éligibles"),
            ("heatmap_quartiers.geojson", "Mini DC — heatmap quartiers"),
        ):
            path = out_dir / fname
            if path.exists():
                details = QgsProcessingContext.LayerDetails(label, context.project(), fname)
                context.addLayerToLoadOnCompletion(str(path), details)
                loaded += 1
        if loaded == 0:
            raise QgsProcessingException(
                self.tr(f"No mini_dc output found in {out_dir} — check the log.")
            )
        feedback.pushInfo(f"Loaded {loaded} layer(s) from {out_dir}")
        return {"OUTPUT_DIR": str(out_dir)}
