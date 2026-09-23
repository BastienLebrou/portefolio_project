"""Draw the ScruTech SVG icons at any size (QIcon leaves these files empty)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent / "assets"


def pixmap(name: str, size: QSize) -> QPixmap:
    """The asset ``name`` drawn to ``size``, keeping its proportions."""
    renderer = QSvgRenderer(str(ASSETS / f"{name}.svg"))
    out = QPixmap(size)
    out.fill(Qt.GlobalColor.transparent)
    if not renderer.isValid():
        return out
    drawn = renderer.defaultSize().scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
    painter = QPainter(out)
    renderer.render(
        painter,
        QRectF(
            (size.width() - drawn.width()) / 2,
            (size.height() - drawn.height()) / 2,
            drawn.width(),
            drawn.height(),
        ),
    )
    painter.end()
    return out
