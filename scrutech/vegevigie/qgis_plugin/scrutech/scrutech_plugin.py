"""ScruTech plugin object: registers the Processing provider with QGIS."""

from __future__ import annotations

import sys
from pathlib import Path

from qgis.core import QgsApplication

# Make the bundled ``vegevigie`` engine importable (packaged next to this file).
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from .provider import ScruTechProvider  # noqa: E402 — after sys.path setup


# QGIS impose une "forme" précise à tout plugin : une classe avec __init__(self, iface)
# (`iface` est l'objet que QGIS fournit pour interagir avec son interface — barre
# d'outils, menus, canevas carte...), puis QGIS appelle lui-même, à des moments précis
# de son cycle de vie, les méthodes `initGui()` (au chargement du plugin) et `unload()`
# (à sa désactivation). Ce n'est pas nous qui appelons ces méthodes : c'est QGIS.
class ScruTechPlugin:
    """Thin QGIS plugin that owns a single Processing provider."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: ScruTechProvider | None = None
        self.action = None

    def initProcessing(self) -> None:  # noqa: N802 — QGIS API name
        # Un "Processing provider" est un groupe d'algorithmes affiché dans la boîte à
        # outils "Traitements" de QGIS (au même titre que les outils natifs de QGIS ou
        # ceux de GRASS/SAGA) : l'enregistrer le rend disponible partout dans QGIS.
        self.provider = ScruTechProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 — QGIS API name
        self.initProcessing()
        # One-click toolbar/menu button that opens the VegeVigie analysis dialog.
        from qgis.PyQt.QtGui import QIcon
        from qgis.PyQt.QtWidgets import QAction

        icon = QIcon(str(_PLUGIN_DIR / "icon.svg"))
        self.action = QAction(
            icon, "ScruTech — Analyze extent (VegeVigie)", self.iface.mainWindow()
        )
        self.action.triggered.connect(self._open_analyze)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("ScruTech", self.action)

    def _open_analyze(self) -> None:
        from qgis import processing

        processing.execAlgorithmDialog("scrutech:analyze_extent", {})

    def unload(self) -> None:
        # Symétrique de initGui()/initProcessing() : quand l'utilisateur désactive ou
        # désinstalle le plugin, QGIS appelle unload() pour qu'on retire proprement tout
        # ce qu'on avait ajouté (bouton, entrée de menu, provider) — sinon ces éléments
        # resteraient affichés alors que le plugin n'est plus actif.
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("ScruTech", self.action)
            self.action = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
