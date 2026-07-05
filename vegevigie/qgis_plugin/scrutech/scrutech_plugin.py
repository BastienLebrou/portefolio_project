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


class ScruTechPlugin:
    """Thin QGIS plugin that owns a single Processing provider."""

    def __init__(self, iface) -> None:
        self.iface = iface
        self.provider: ScruTechProvider | None = None

    def initProcessing(self) -> None:  # noqa: N802 — QGIS API name
        self.provider = ScruTechProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self) -> None:  # noqa: N802 — QGIS API name
        self.initProcessing()

    def unload(self) -> None:
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
