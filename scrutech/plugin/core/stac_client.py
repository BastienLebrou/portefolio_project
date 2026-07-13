"""Recherche STAC multi-catalogue — Palier 1.

CDSE et Microsoft Planetary Computer interrogés en parallèle. Fonctionnel
sans clé API pour un premier test (MPC expose une partie de son catalogue
sans authentification).
"""

from dataclasses import dataclass
from datetime import date


@dataclass
class BBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass
class SceneResult:
    catalog: str  # "cdse" | "mpc"
    item_id: str
    collection: str
    datetime_acquired: date
    cloud_cover_pct: float | None
    cog_asset_url: str
    thumbnail_url: str | None
    footprint_geojson: dict


class StacClient:
    def search(
        self,
        bbox: BBox,
        date_from: date,
        date_to: date,
        collections: list[str],
        max_cloud_cover_pct: float | None = None,
    ) -> list[SceneResult]:
        """Interroge CDSE + MPC en parallèle, fusionne et déduplique les résultats."""
        raise NotImplementedError

    def get_thumbnail(self, scene: SceneResult) -> bytes:
        raise NotImplementedError
