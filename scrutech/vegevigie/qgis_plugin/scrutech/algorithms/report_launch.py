"""Launch the ScruTech visual report (Streamlit) for an area of interest.

Starts the Streamlit report in the external Python (detached) and opens it in the browser;
it reads the outputs cached for the area in the central store. QGIS can't host a live
Streamlit server in a dock, so the browser is the robust option that always works.
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
    QgsProcessingParameterNumber,
)
from qgis.PyQt.QtCore import QCoreApplication

from . import _qgis_compat as _compat
from ._venv import python_param, require_python

# Located inside the external Python, so it works for the dev venv and ~/.scrutech/venv alike.
_FIND_APP = (
    "import importlib.util as u; s = u.find_spec('vegevigie.report.app'); "
    "print(s.origin if s else '')"
)


class ReportLaunchAlgorithm(QgsProcessingAlgorithm):
    """Open the live ScruTech visual report for an area of interest."""

    EXTENT = "EXTENT"
    PORT = "PORT"
    PYTHON_EXE = "PYTHON_EXE"

    def name(self) -> str:
        return "report_launch"

    def displayName(self) -> str:  # noqa: N802
        return self.tr("Rapport visuel dans le navigateur")

    def group(self) -> str:
        return self.tr("4 · Consulter les résultats")

    def groupId(self) -> str:  # noqa: N802
        return "restituer"

    def shortHelpString(self) -> str:  # noqa: N802
        return self.tr(
            "<p>Ouvre dans votre navigateur un <b>rapport de synthèse</b> de la zone : carte et "
            "chiffres clés de chaque analyse déjà faite dessus (VegeVigie, AlphaEarth, PAFF, "
            "écobuage, Biotrame).</p>"
            "<p><b>Avant de lancer</b><br>Avoir analysé la zone avec au moins un outil des "
            "groupes 2 ou 3.</p>"
            "<p><b>Étapes</b><br>"
            "1. Zone d'étude : <b>la même emprise</b> que celle des analyses.<br>"
            "2. Exécuter : le rapport s'ouvre dans le navigateur au bout de quelques "
            "secondes.</p>"
            "<p><b>Bon à savoir</b><br>Le rapport tourne uniquement sur votre ordinateur "
            "(adresse locale, inaccessible depuis le réseau). Son bouton « Rafraîchir les "
            "sorties » ajoute les analyses lancées entre-temps.</p>"
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
            QgsProcessingParameterExtent(
                self.EXTENT, self.tr("Zone d'étude (la même emprise que les analyses)")
            )
        )
        self.addParameter(
            _compat.advanced(
                QgsProcessingParameterNumber(
                    self.PORT,
                    self.tr("Port local"),
                    type=_compat.NUMBER_INTEGER,
                    defaultValue=8501,
                    minValue=1024,
                    maxValue=65535,
                )
            )
        )
        self.addParameter(python_param(self.PYTHON_EXE))

    def processAlgorithm(  # noqa: N802
        self,
        parameters: dict,
        context: QgsProcessingContext,
        feedback: QgsProcessingFeedback,
    ) -> dict:
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        rect = self.parameterAsExtent(parameters, self.EXTENT, context, crs=wgs84)
        if rect.isEmpty():
            raise QgsProcessingException(
                self.tr("La zone d'étude est vide : choisissez une emprise.")
            )
        bbox = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        aoi_id = "bbox-" + "_".join(f"{value:.4f}" for value in bbox)
        port = self.parameterAsInt(parameters, self.PORT, context)

        python_exe = require_python(
            self.parameterAsString(parameters, self.PYTHON_EXE, context).strip(), feedback
        )
        app = self._report_app(python_exe)
        if app is None:
            raise QgsProcessingException(
                self.tr(
                    "Le rapport est introuvable dans le Python de ScruTech. Relancez « Vérifier "
                    "et installer ScruTech » en cochant « Installer ou mettre à jour »."
                )
            )

        port = self._free_port(port)
        url = f"http://localhost:{port}"
        self._launch(python_exe, app, aoi_id, port, feedback)
        time.sleep(3)  # give Streamlit a moment to boot before opening the browser
        webbrowser.open(url)
        feedback.pushInfo(f"Rapport ScruTech : {url} (zone : {aoi_id})")
        return {"URL": url}

    # --- helpers -------------------------------------------------------------
    @staticmethod
    def _report_app(python_exe: str) -> Path | None:
        from ._external import _ENV_STRIP

        env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
        try:
            out = subprocess.run(
                [python_exe, "-c", _FIND_APP],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        origin = out.stdout.strip()
        return Path(origin) if origin and Path(origin).is_file() else None

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
        feedback.pushInfo("Lancement : " + " ".join(cmd))
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
