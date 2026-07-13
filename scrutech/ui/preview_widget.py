"""Aperçu vignette avant tout chargement plein résolution — Palier 1."""

from qgis.PyQt.QtWidgets import QWidget

from ..core.stac_client import SceneResult


class PreviewWidget(QWidget):
    def show_scene(self, scene: SceneResult) -> None:
        raise NotImplementedError

    def show_metadata(self, scene: SceneResult) -> None:
        """Date, capteur, % nuages, lien asset COG."""
        raise NotImplementedError
