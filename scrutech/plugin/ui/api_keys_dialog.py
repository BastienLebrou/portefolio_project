"""Formulaire de configuration des clés API.

Écrit exclusivement dans QgsAuthManager via core.auth_manager — jamais
dans settings.ini ni dans le projet .qgz.
"""

from qgis.PyQt.QtWidgets import QDialog

from ..core.auth_manager import AuthManager, Provider


class ApiKeysDialog(QDialog):
    def __init__(self, auth_manager: AuthManager):
        super().__init__()
        self.auth_manager = auth_manager
        self.setWindowTitle("Configurer les clés API")

    def save_provider_credentials(self, provider: Provider, **fields: str) -> None:
        raise NotImplementedError

    def refresh_status_indicators(self) -> None:
        """Affiche quel fournisseur est configuré, sans jamais montrer la clé en clair."""
        raise NotImplementedError
