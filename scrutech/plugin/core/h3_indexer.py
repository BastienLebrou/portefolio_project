"""Indexation H3 des footprints de recherche — Palier 3.

Permet des requêtes "quelles scènes couvrent ces 200 communes" sans
jointure géométrique coûteuse. Résolution H3 adaptée au niveau de zoom
QGIS courant.
"""

from .stac_client import SceneResult


class H3Indexer:
    # Plus on est dézoomé (grande échelle), moins il est utile d'indexer finement : une
    # résolution H3 basse (grands hexagones) suffit et reste rapide ; en zoomant, une
    # résolution plus fine devient nécessaire pour distinguer des scènes proches.
    def resolution_for_zoom(self, qgis_scale: float) -> int:
        """Choisit la résolution H3 (0-15) adaptée à l'échelle de la carte."""
        raise NotImplementedError

    # L'idée d'index inversé : au lieu de tester "cette scène couvre-t-elle cette
    # commune ?" pour chaque paire (coûteux à grande échelle), on précalcule une fois
    # {cellule_h3: [scènes qui la couvrent]} — répondre "quelles scènes couvrent la
    # zone X ?" devient alors juste un lookup par cellule, plus une jointure géométrique.
    def index_scenes(self, scenes: list[SceneResult], resolution: int) -> dict[str, list[str]]:
        """Retourne {cellule_h3: [item_id, ...]}."""
        raise NotImplementedError

    def cells_covering(self, geojson_geometry: dict, resolution: int) -> set[str]:
        raise NotImplementedError
