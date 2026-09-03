"""Aperçu vignette avant tout chargement plein résolution — Palier 1."""

from qgis.PyQt.QtWidgets import QWidget

from ..core.stac_client import SceneResult


# QWidget est la classe de base la plus générique de Qt pour un élément d'interface :
# contrairement à QDialog (fenêtre ponctuelle) ou QDockWidget (panneau ancrable), un
# QWidget "nu" est destiné à être intégré À L'INTÉRIEUR d'un autre widget (ici, dans le
# search_panel qui affichera l'aperçu d'une scène sélectionnée).
class PreviewWidget(QWidget):
    def show_scene(self, scene: SceneResult) -> None:
        raise NotImplementedError

    def show_metadata(self, scene: SceneResult) -> None:
        """Date, capteur, % nuages, lien asset COG."""
        raise NotImplementedError
