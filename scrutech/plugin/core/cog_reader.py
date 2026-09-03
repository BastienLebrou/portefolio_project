"""Lecture COG en streaming — Palier 2.

Charge un asset COG directement dans le canvas QGIS via GDAL /vsicurl/ ou
/vsis3/, sans jamais créer de fichier local sauf action explicite de
l'utilisateur (voir cache_manager.py).
"""

from qgis.core import QgsRasterLayer

from .stac_client import SceneResult


class CogReader:
    # /vsicurl/ est un "système de fichiers virtuel" de GDAL qui fait comme si une URL
    # HTTP distante était un fichier local — sans jamais le télécharger en entier : GDAL
    # ne lit QUE les octets nécessaires (grâce aux index internes d'un COG, voir le
    # docstring du module) pour afficher juste la zone/le niveau de zoom demandé. C'est
    # ce qui permet à QGIS d'ouvrir une image satellite de plusieurs Go instantanément.
    def open_as_layer(self, scene: SceneResult, layer_name: str | None = None) -> QgsRasterLayer:
        """Construit l'URI GDAL vsicurl et retourne un QgsRasterLayer non chargé en mémoire."""
        raise NotImplementedError

    def cache_locally(self, scene: SceneResult, destination_path: str) -> str:
        """Téléchargement explicite — seul chemin qui écrit un GeoTIFF complet sur disque."""
        raise NotImplementedError
