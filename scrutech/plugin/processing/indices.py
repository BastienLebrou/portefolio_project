"""Indices spectraux (NDVI, NDWI, ...) — Palier 4.

Bascule coût-consciente : zone < seuil → calcul local (numpy/rasterio sur
la fenêtre visible) ; zone > seuil → délégation à Sentinel Hub Processing
API ou Google Earth Engine, avec estimation de coût affichée avant exécution.
"""

from dataclasses import dataclass
from enum import Enum

DEFAULT_LOCAL_AREA_THRESHOLD_KM2 = 50.0


class IndexType(str, Enum):
    NDVI = "ndvi"
    NDWI = "ndwi"
    NDMI = "ndmi"


@dataclass
class CostEstimate:
    execution_mode: str  # "local" | "sentinel_hub" | "gee"
    estimated_processing_units: float | None
    estimated_requests: int | None


class IndicesProcessor:
    def __init__(self, local_area_threshold_km2: float = DEFAULT_LOCAL_AREA_THRESHOLD_KM2):
        self.local_area_threshold_km2 = local_area_threshold_km2

    def choose_execution_mode(self, area_km2: float) -> str:
        raise NotImplementedError

    def estimate_cost(self, index_type: IndexType, area_km2: float) -> CostEstimate:
        raise NotImplementedError

    def compute_local(self, index_type: IndexType, raster_path: str) -> str:
        raise NotImplementedError

    def compute_delegated(self, index_type: IndexType, bbox, date_range) -> str:
        raise NotImplementedError
