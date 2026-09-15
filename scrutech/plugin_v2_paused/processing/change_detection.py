"""Détection de changement (CCDC/BFAST) — Palier 4, partie avancée.

Toujours délégué à Google Earth Engine si une clé est configurée — ces
algorithmes sont trop coûteux pour un calcul local raisonnable sur des
séries temporelles denses (cf. fiche Séries temporelles denses - CCDC
BFAST LandTrendr).
"""

from enum import Enum


class Algorithm(str, Enum):
    CCDC = "ccdc"
    BFAST = "bfast"


class ChangeDetectionProcessor:
    def requires_gee(self) -> bool:
        return True

    def run(self, algorithm: Algorithm, bbox, date_from, date_to) -> str:
        """Soumet le calcul à Google Earth Engine, retourne l'URL de l'export."""
        raise NotImplementedError
