"""Inférence foundation model EO (Clay/Prithvi) — Palier 5.

Mode local (ONNX quantifié) implémenté en premier ; le mode distant (API
d'inférence hébergée séparément) n'est qu'une interface ici, hors scope
de ce plugin.
"""

from dataclasses import dataclass
from enum import Enum


class InferenceMode(str, Enum):
    LOCAL_ONNX = "local_onnx"
    REMOTE_API = "remote_api"  # interface seulement, non implémenté dans ce plugin


@dataclass
class Detection:
    geometry_geojson: dict
    confidence: float
    label: str


class InferenceProcessor:
    def run_local(self, raster_path: str, model_path: str, label: str) -> list[Detection]:
        """Détection (ex : panneaux solaires) sur une zone dessinée dans QGIS."""
        raise NotImplementedError

    def run_remote(self, raster_path: str, endpoint_url: str, auth_cfg_id: str) -> list[Detection]:
        raise NotImplementedError
