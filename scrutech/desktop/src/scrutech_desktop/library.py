"""The library: the shelf of ScruTech applications, one tile each.

Click a tile, its application opens. Adding a project to :mod:`catalog` adds a tile here.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .catalog import APPLICATIONS, Application
from .icons import pixmap

_COLUMNS = 3


class Tile(QFrame):
    """One application: its icon, its name, what it does."""

    clicked = Signal(str)

    def __init__(self, app: Application, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.setObjectName("tile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(104)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 14, 16, 14)
        row.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(pixmap(app.icon, QSize(44, 44)))
        icon.setFixedWidth(48)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        name = QLabel(app.name)
        name.setObjectName("tileName")
        tagline = QLabel(app.tagline)
        tagline.setObjectName("tileText")
        tagline.setWordWrap(True)
        text.addWidget(name)
        text.addWidget(tagline)
        row.addLayout(text, 1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt API name
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.app.key)
        super().mouseReleaseEvent(event)


class LibraryPage(QScrollArea):
    """Every application of the catalogue, in a grid of tiles."""

    opened = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(24, 8, 24, 24)
        grid.setSpacing(16)
        for i, app in enumerate(APPLICATIONS):
            tile = Tile(app)
            tile.clicked.connect(self.opened)
            grid.addWidget(tile, i // _COLUMNS, i % _COLUMNS)
        grid.setRowStretch(grid.rowCount(), 1)
        self.setWidget(inner)
