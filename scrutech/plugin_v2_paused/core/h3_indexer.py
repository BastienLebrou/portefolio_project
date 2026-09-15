"""Indexation H3 des footprints de recherche — Palier 3.

Permet des requêtes "quelles scènes couvrent ces 200 communes" sans
jointure géométrique coûteuse. Résolution H3 adaptée au niveau de zoom
QGIS courant.
"""

from .stac_client import SceneResult


class H3Indexer:
    def resolution_for_zoom(self, qgis_scale: float) -> int:
        """Choisit la résolution H3 (0-15) adaptée à l'échelle de la carte."""
        raise NotImplementedError

    def index_scenes(self, scenes: list[SceneResult], resolution: int) -> dict[str, list[str]]:
        """Retourne {cellule_h3: [item_id, ...]}."""
        raise NotImplementedError

    def cells_covering(self, geojson_geometry: dict, resolution: int) -> set[str]:
        raise NotImplementedError
