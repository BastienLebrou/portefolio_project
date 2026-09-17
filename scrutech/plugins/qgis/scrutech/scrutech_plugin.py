"""ScruTech plugin object: registers the Processing provider and guides a first use."""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.core import QgsApplication, QgsProcessingFeedback

# Make the flat ``ecobuage`` engine (bundled next to this file) importable by the native
# écobuage tool.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from .provider import ScruTechProvider  # noqa: E402 — after sys.path setup

_MENU = "ScruTech"
_TITLE = "ScruTech"


class ScruTechPlugin:
    """Thin QGIS plugin that owns a single Processing provider."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: ScruTechProvider | None = None
        self.actions: list = []
        self._install = None  # (task, context, feedback) kept alive while installing

    def initProcessing(self) -> None:  # noqa: N802 — QGIS API name
        self.provider = ScruTechProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 — QGIS API name
        self.initProcessing()
        from qgis.PyQt.QtGui import QIcon
        from qgis.PyQt.QtWidgets import QAction

        icon = QIcon(str(_PLUGIN_DIR / "icon.svg"))
        for text, algorithm_id in (
            ("Diagnostic complet (clé en main)", "scrutech:diagnostic_complet"),
            ("Vérifier et installer ScruTech (clé GEE, GeoAI)", "scrutech:setup_check"),
        ):
            action = QAction(icon, text, self.iface.mainWindow())
            action.triggered.connect(lambda _=False, alg=algorithm_id: self._open(alg))
            self.iface.addPluginToMenu(_MENU, action)
            self.actions.append(action)
        self.iface.addToolBarIcon(self.actions[0])
        self._guide_first_use()

    def _open(self, algorithm_id: str, parameters: dict | None = None) -> None:
        from qgis import processing

        processing.execAlgorithmDialog(algorithm_id, parameters or {})

    # --- first use -------------------------------------------------------------
    def _guide_first_use(self) -> None:
        """No external Python yet: offer to install it in one click, right when QGIS loads."""
        from .algorithms._venv import find_python

        if find_python(_PLUGIN_DIR):
            return
        self._message(
            "Bienvenue. Une installation unique prépare les calculs de ScruTech : environ 1 Go, "
            "5 à 15 minutes, sans modifier QGIS.",
            "info",
            [
                ("Installer maintenant", self._install_in_background),
                ("Options (clé GEE, GeoAI)", self._setup_dialog),
            ],
        )

    def _setup_dialog(self) -> None:
        self._open("scrutech:setup_check", {"INSTALL": True})

    def _install_in_background(self) -> None:
        """Run « Vérifier et installer » as a QGIS task: progress at the bottom, cancellable."""
        from qgis.core import QgsProcessingAlgRunnerTask, QgsProcessingContext

        if self._install is not None:
            return
        self.iface.messageBar().clearWidgets()
        algorithm = QgsApplication.processingRegistry().createAlgorithmById("scrutech:setup_check")
        context, feedback = QgsProcessingContext(), QgsProcessingFeedback()
        task = QgsProcessingAlgRunnerTask(algorithm, {"INSTALL": True}, context, feedback)
        task.executed.connect(self._installed)
        self._install = (task, context, feedback)
        QgsApplication.taskManager().addTask(task)
        self._message(
            "Installation en cours, suivie dans la barre des tâches en bas de QGIS. Vous "
            "pouvez continuer à travailler.",
            "info",
            [],
            duration=15,
        )

    def _installed(self, successful: bool, results: dict) -> None:
        _task, _context, feedback = self._install
        self._install = None
        self.iface.messageBar().clearWidgets()
        if successful and results.get("PRET"):
            self._message(
                "ScruTech est prêt. Lancez un premier diagnostic de votre zone.",
                "success",
                [("Diagnostic complet", lambda: self._open("scrutech:diagnostic_complet"))],
            )
            return
        from .algorithms._setup import install_problem

        reason = install_problem(feedback.textLog())
        self._message(
            f"L'installation de ScruTech n'a pas abouti : {reason}",
            "critical",
            [("Voir le détail et réessayer", self._setup_dialog)],
        )

    def _message(self, text: str, level: str, buttons: list, duration: int = 0) -> None:
        from qgis.core import Qgis
        from qgis.PyQt.QtWidgets import QPushButton

        levels = getattr(Qgis, "MessageLevel", Qgis)
        bar = self.iface.messageBar()
        item = bar.createMessage(_TITLE, text)
        for label, callback in buttons:
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, run=callback: run())
            item.layout().addWidget(button)
        bar.pushWidget(item, getattr(levels, level.capitalize()), duration)

    def unload(self) -> None:
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
            self.iface.removePluginMenu(_MENU, action)
        self.actions = []
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
