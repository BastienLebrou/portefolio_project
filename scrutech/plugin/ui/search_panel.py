"""Panneau de recherche — Palier 1.

bbox = emprise du canvas QGIS actif. Résultats affichés en footprints
vectoriels temporaires, jamais de raster chargé à ce stade.
"""

from qgis.PyQt.QtWidgets import QDockWidget
from qgis.gui import QgisInterface

from ..core.stac_client import StacClient


class SearchPanel(QDockWidget):
    def __init__(self, iface: QgisInterface, stac_client: StacClient):
        super().__init__("Rechercher des images satellite")
        self.iface = iface
        self.stac_client = stac_client

    def current_canvas_bbox(self):
        raise NotImplementedError

    def run_search(self) -> None:
        raise NotImplementedError

    def render_results_as_temporary_layer(self, results) -> None:
        raise NotImplementedError
