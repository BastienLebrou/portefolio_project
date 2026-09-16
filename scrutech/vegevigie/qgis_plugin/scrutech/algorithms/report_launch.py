"""Launch the ScruTech visual report (Streamlit) for an area of interest.

Point it at a folder where ScruTech algorithms wrote their outputs; this starts the
Streamlit report in the project venv (detached) and opens it in the browser. QGIS can't
host a live Streamlit server in a dock, so the report opens in the default browser — the
robust option that always works.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import webbrowser
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
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat


class ReportLaunchAlgorithm(QgsProcessingAlgorithm):
    """Open the live ScruTech visual report for an area of interest."""

    EXTENT = "EXTENT"
    PORT = "PORT"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "report_launch"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("① Rapport visuel (Streamlit)")

    def group(self) -> str:
        return self.tr("4 · Restituer")

    def groupId(self) -> str:  # noqa: N802
        return "restituer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "Open an interactive visual report of a ScruTech analysis: the map + metrics of "
            "every pillar output found in the folder (biotrame, écobuage, VegeVigie, PAF, "
            "AlphaEarth). Starts a Streamlit app in the project venv and opens it in the "
            "browser. Outputs are selected from the central store for the chosen area."
        )

    def createInstance(self) -> ReportLaunchAlgorithm:  # noqa: N802
        return ReportLaunchAlgorithm()

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
                self.PORT,
                self.tr("Local port"),
                type=_compat.NUMBER_INTEGER,
                defaultValue=8501,
                minValue=1024,
                maxValue=65535,
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
        aoi_id = "bbox-" + "_".join(f"{value:.4f}" for value in bbox)
        port = self.parameterAsInt(parameters, self.PORT, context)

        explicit = self.parameterAsString(parameters, self.PYTHON_EXE, context).strip()
        python_exe = self._resolve_python(explicit, feedback)
        if not python_exe:
            raise QgsProcessingException(
                self.tr(
                    "No VegeVigie interpreter found (needs streamlit). Point 'Python "
                    "executable' at the project venv."
                )
            )
        app = Path(python_exe).parents[2] / "src" / "vegevigie" / "report" / "app.py"
        if not app.exists():
            raise QgsProcessingException(self.tr("Report app not found at {}").format(app))

        port = self._free_port(port)
        url = f"http://localhost:{port}"
        self._launch(python_exe, app, aoi_id, port, feedback)
        time.sleep(3)  # give Streamlit a moment to boot before opening the browser
        webbrowser.open(url)
        feedback.pushInfo(f"ScruTech report: {url} (AOI: {aoi_id})")
        return {"URL": url}

    # --- helpers -------------------------------------------------------------
    def _launch(self, python_exe: str, app: Path, aoi_id: str, port: int, feedback) -> None:
        from ._external import _ENV_STRIP

        cmd = [
            python_exe,
            "-m",
            "streamlit",
            "run",
            str(app),
            "--server.port",
            str(port),
            # Bind to loopback only: the report holds local analysis data and must not be
            # reachable from the LAN/WAN (Streamlit otherwise listens on 0.0.0.0).
            "--server.address",
            "127.0.0.1",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ]

        # The report only needs the AOI id; never hand credentials to it (it renders
        # local data and has no use for GEE/R2 secrets) — least privilege for the child.
        def _is_secret(k: str) -> bool:
            up = k.upper()
            return up.startswith(("R2_", "AWS_")) or any(
                s in up for s in ("SECRET", "CREDENTIAL", "TOKEN", "PASSWORD")
            )

        env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP and not _is_secret(k)}
        env["SCRUTECH_AOI_ID"] = aoi_id
        feedback.pushInfo("Launching: " + " ".join(cmd))
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(cmd, env=env, creationflags=flags)

    def _free_port(self, start: int) -> int:
        """Return ``start`` if free, else the next free port (so the URL is correct)."""
        for port in range(start, start + 20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    return port
        return start

    def _resolve_python(self, explicit: str, feedback) -> str:
        from ._venv import resolve

        plugin_root = Path(__file__).resolve().parents[1]
        project_dir = plugin_root.parents[1]
        python_exe = resolve(plugin_root, explicit, project_dir, feedback)
        if python_exe:
            feedback.pushInfo(f"VegeVigie interpreter: {python_exe}")
        return python_exe
