"""ScruTech plugin object: registers the Processing provider and guides a first use."""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.core import QgsApplication

# Make the flat ``ecobuage`` engine (bundled next to this file) importable by the native
# écobuage tool.
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from .provider import ScruTechProvider  # noqa: E402 — after sys.path setup

_MENU = "ScruTech"


class ScruTechPlugin:
    """Thin QGIS plugin that owns a single Processing provider."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: ScruTechProvider | None = None
        self.actions: list = []

    def initProcessing(self) -> None:  # noqa: N802 — QGIS API name
        self.provider = ScruTechProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 — QGIS API name
        self.initProcessing()
        from qgis.PyQt.QtGui import QIcon
        from qgis.PyQt.QtWidgets import QAction

        icon = QIcon(str(_PLUGIN_DIR / "icon.svg"))
        for text, algorithm_id in (
            ("Vérifier et installer ScruTech", "scrutech:setup_check"),
            ("Analyser la végétation d'une emprise (VegeVigie)", "scrutech:analyze_extent"),
        ):
            action = QAction(icon, text, self.iface.mainWindow())
            action.triggered.connect(lambda _=False, alg=algorithm_id: self._open(alg))
            self.iface.addPluginToMenu(_MENU, action)
            self.actions.append(action)
        self.iface.addToolBarIcon(self.actions[-1])
        self._guide_first_use()

    def _open(self, algorithm_id: str) -> None:
        from qgis import processing

        processing.execAlgorithmDialog(algorithm_id, {})

    def _guide_first_use(self) -> None:
        """No external Python yet: point the user at the setup tool, right in QGIS."""
        from .algorithms._venv import find_python

        if find_python(_PLUGIN_DIR):
            return
        from qgis.core import Qgis
        from qgis.PyQt.QtWidgets import QPushButton

        bar = self.iface.messageBar()
        item = bar.createMessage(
            "ScruTech",
            "Première utilisation : lancez « Vérifier et installer ScruTech » pour préparer "
            "les outils.",
        )
        button = QPushButton("Vérifier et installer")
        button.clicked.connect(lambda: self._open("scrutech:setup_check"))
        item.layout().addWidget(button)
        bar.pushWidget(item, getattr(Qgis, "MessageLevel", Qgis).Info)

    def unload(self) -> None:
        for action in self.actions:
            self.iface.removeToolBarIcon(action)
            self.iface.removePluginMenu(_MENU, action)
        self.actions = []
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
