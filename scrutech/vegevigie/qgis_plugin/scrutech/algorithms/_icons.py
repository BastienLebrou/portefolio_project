"""Shared icon loader for ScruTech Processing algorithms (ScruTech charter)."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtGui import QIcon


def algo_icon(name: str) -> QIcon:
    """Return the badge ``icons/<name>.svg`` shipped in the plugin folder."""
    path = Path(__file__).resolve().parents[1] / "icons" / f"{name}.svg"
    return QIcon(str(path))
