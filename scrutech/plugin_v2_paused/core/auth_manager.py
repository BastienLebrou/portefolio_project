"""Stockage des clés API via QgsAuthManager — jamais en clair sur disque.

Étape 3 de l'ordre d'exécution : ce module est implémenté avant tout le
reste, car stac_client, processing/* et ui/* en dépendent tous.
"""

from dataclasses import dataclass
from enum import Enum


class Provider(str, Enum):
    COPERNICUS_DATASPACE = "cdse"
    SENTINEL_HUB = "sentinel_hub"
    PLANET_LABS = "planet"
    GOOGLE_EARTH_ENGINE = "gee"
    MICROSOFT_PLANETARY_COMPUTER = "mpc"


@dataclass
class Credentials:
    provider: Provider
    auth_cfg_id: str  # identifiant QgsAuthMethodConfig, pas la clé elle-même


class AuthManager:
    """Wrapper autour de QgsApplication.authManager().

    Ne JAMAIS exposer la valeur brute d'une clé en dehors de ce module —
    les autres modules ne manipulent que des `Credentials` (un id de config),
    la résolution en valeur réelle se fait au point d'appel HTTP uniquement.
    """

    def save_credentials(self, provider: Provider, **fields: str) -> Credentials:
        raise NotImplementedError

    def get_credentials(self, provider: Provider) -> Credentials | None:
        raise NotImplementedError

    def delete_credentials(self, provider: Provider) -> None:
        raise NotImplementedError

    def has_credentials(self, provider: Provider) -> bool:
        raise NotImplementedError
