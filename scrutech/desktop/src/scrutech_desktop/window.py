"""The ScruTech window: a header, the library of applications, and one page per application."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import settings
from .catalog import BY_KEY
from .config_page import ConfigPage
from .icons import ASSETS, pixmap
from .library import LibraryPage
from .run_page import RunPage


class MainWindow(QMainWindow):
    """One window: the library, the configuration, and the open applications."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ScruTech")
        self.setWindowIcon(QIcon(str(ASSETS / "mantis-emblem.svg")))
        self.pages = QStackedWidget()
        self.library = LibraryPage()
        self.library.opened.connect(self.open_application)
        self.config = ConfigPage()
        self.pages.addWidget(self.library)
        self.pages.addWidget(self.config)
        self._open: dict[str, RunPage] = {}

        central = QWidget()
        box = QVBoxLayout(central)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self._header())
        box.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.show_library()

    def _header(self) -> QWidget:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(24, 18, 24, 12)
        row.setSpacing(16)
        logo = QLabel()
        logo.setPixmap(pixmap("scrutech-logo", QSize(240, 64)))
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("Applications")
        self.title.setObjectName("title")
        self.subtitle = QLabel("Choisissez une application pour analyser un territoire.")
        self.subtitle.setObjectName("subtitle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        row.addLayout(titles, 1)
        self.back_button = QPushButton("← Applications")
        self.back_button.clicked.connect(self.show_library)
        config_button = QPushButton("Configuration")
        config_button.clicked.connect(self.show_config)
        row.addWidget(self.back_button)
        row.addWidget(config_button)
        return header

    # --- navigation ------------------------------------------------------------
    def show_library(self) -> None:
        self._head("Applications", "Choisissez une application pour analyser un territoire.")
        self.pages.setCurrentWidget(self.library)
        self.back_button.setVisible(False)

    def show_config(self) -> None:
        self.config.refresh()
        self._head("Configuration", "Le moteur, le dossier des analyses et la clé Earth Engine.")
        self.pages.setCurrentWidget(self.config)
        self.back_button.setVisible(True)

    def open_application(self, key: str) -> None:
        app = BY_KEY[key]
        page = self._open.get(key)
        if page is None:
            page = RunPage(app)
            page.needs_setup.connect(self.show_config)
            self._open[key] = page
            self.pages.addWidget(page)
        self._head(app.name, app.tagline)
        self.pages.setCurrentWidget(page)
        self.back_button.setVisible(True)

    def _head(self, title: str, subtitle: str) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)

    def first_run_hint(self) -> None:
        """No engine yet: start on the configuration, where the install button is."""
        if not settings.engine_python():
            self.show_config()
