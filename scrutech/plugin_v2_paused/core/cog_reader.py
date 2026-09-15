"""Lecture COG en streaming — Palier 2.

Charge un asset COG directement dans le canvas QGIS via GDAL /vsicurl/ ou
/vsis3/, sans jamais créer de fichier local sauf action explicite de
l'utilisateur (voir cache_manager.py).
"""

from qgis.core import QgsRasterLayer

from .stac_client import SceneResult


class CogReader:
    def open_as_layer(self, scene: SceneResult, layer_name: str | None = None) -> QgsRasterLayer:
        """Construit l'URI GDAL vsicurl et retourne un QgsRasterLayer non chargé en mémoire."""
        raise NotImplementedError

    def cache_locally(self, scene: SceneResult, destination_path: str) -> str:
        """Téléchargement explicite — seul chemin qui écrit un GeoTIFF complet sur disque."""
        raise NotImplementedError
