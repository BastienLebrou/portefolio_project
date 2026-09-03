"""Wrapper QgsTask pour les appels réseau asynchrones.

Contrainte n°2 : aucun appel réseau bloquant dans le thread UI. Tout passe
par ce module.
"""

from collections.abc import Callable
from typing import Any

# QgsTask est le mécanisme QGIS pour exécuter du travail EN ARRIÈRE-PLAN (un thread à
# part) sans geler l'interface : `run()` s'exécute hors du thread principal (c'est là
# qu'on met l'appel réseau bloquant), puis QGIS rappelle `finished()` sur le thread
# principal une fois terminé (c'est là, et SEULEMENT là, qu'on a le droit de toucher
# à l'interface graphique).
from qgis.core import QgsTask


class ApiJob(QgsTask):
    def __init__(self, description: str, work_fn: Callable[[], Any], on_finished: Callable[[Any], None]):
        super().__init__(description, QgsTask.CanCancel)
        self._work_fn = work_fn
        self._on_finished = on_finished
        self._result: Any = None

    def run(self) -> bool:
        raise NotImplementedError

    def finished(self, result: bool) -> None:
        raise NotImplementedError


class JobRunner:
    def submit(self, description: str, work_fn: Callable[[], Any], on_finished: Callable[[Any], None]) -> ApiJob:
        raise NotImplementedError
