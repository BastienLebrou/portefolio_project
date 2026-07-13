# 🎓 QGIS 4.0 / Qt6 : QAction a déménagé de QtWidgets vers QtGui (cf. notes
# de migration, docs/qgis4_migration_notes.md). On importe via qgis.PyQt —
# le shim neutre Qt5/Qt6 fourni par QGIS — plutôt que PyQt5/PyQt6
# directement, pour que ce fichier tourne sans modification sur QGIS 3.x et
# QGIS 4.x pendant la période de transition.
from qgis.PyQt.QtGui import QAction, QIcon
from qgis.gui import QgisInterface

PLUGIN_NAME = "GeoData Engineer"


class GeoDataEngineerPlugin:
    """Point d'entrée du plugin. Enregistre les actions de la barre d'outils
    et les panneaux. Aucune logique métier ici — délègue tout aux modules
    core/, processing/, ui/.
    """

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.actions: list[QAction] = []
        self.menu = PLUGIN_NAME

        self.search_panel = None
        self.api_keys_dialog = None
        self.job_monitor = None

    def initGui(self) -> None:
        self._add_action(
            icon_path="resources/icons/search.png",
            text="Rechercher des images satellite",
            callback=self.open_search_panel,
        )
        self._add_action(
            icon_path="resources/icons/key.png",
            text="Configurer les clés API",
            callback=self.open_api_keys_dialog,
        )
        self._add_action(
            icon_path="resources/icons/monitor.png",
            text="Suivi des tâches",
            callback=self.open_job_monitor,
        )

    def unload(self) -> None:
        for action in self.actions:
            self.iface.removePluginRasterMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

    def _add_action(self, icon_path: str, text: str, callback) -> None:
        action = QAction(QIcon(icon_path), text, self.iface.mainWindow())
        action.triggered.connect(callback)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToRasterMenu(self.menu, action)
        self.actions.append(action)

    def open_search_panel(self) -> None:
        raise NotImplementedError("ui.search_panel — Palier 1")

    def open_api_keys_dialog(self) -> None:
        raise NotImplementedError("ui.api_keys_dialog — clés API sécurisées")

    def open_job_monitor(self) -> None:
        raise NotImplementedError("ui.job_monitor — suivi des tâches asynchrones")
