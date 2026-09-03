"""Suivi des tâches asynchrones — progress, logs, coût API estimé.

Contrainte n°5 : chaque appel API loggé (endpoint, paramètres, code retour,
latence) dans un fichier dédié, consultable depuis ce panneau.
"""

from qgis.PyQt.QtWidgets import QDockWidget

from ..core.job_runner import ApiJob


class JobMonitor(QDockWidget):
    def __init__(self):
        super().__init__("Suivi des tâches")

    def register_job(self, job: ApiJob) -> None:
        raise NotImplementedError

    # Signature riche mais pas de logique encore (scaffold) : elle documente déjà
    # QUOI journaliser pour chaque appel API (contrainte n°5 du module docstring) —
    # l'implémentation viendra écrire ces informations dans le fichier de log dédié.
    def append_log_entry(
        self, endpoint: str, params: dict, status_code: int, latency_ms: float
    ) -> None:
        raise NotImplementedError
