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
    # Contrairement aux autres processors du plugin (qui basculent local/distant selon
    # la taille de la zone), celui-ci délègue TOUJOURS à Earth Engine : ces algorithmes
    # analysent des séries temporelles denses (des centaines d'images par pixel), un
    # volume de calcul qui dépasse largement ce qu'une machine locale peut faire de
    # façon raisonnable — d'où `requires_gee()` qui renvoie toujours True, sans condition.
    def requires_gee(self) -> bool:
        return True

    def run(self, algorithm: Algorithm, bbox, date_from, date_to) -> str:
        """Soumet le calcul à Google Earth Engine, retourne l'URL de l'export."""
        raise NotImplementedError
