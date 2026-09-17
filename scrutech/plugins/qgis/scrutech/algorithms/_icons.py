"""Shared icon loader for ScruTech Processing algorithms (ScruTech charter)."""

from __future__ import annotations

from pathlib import Path

from qgis.PyQt.QtGui import QIcon


def algo_icon(name: str) -> QIcon:
    """Return the badge ``icons/<name>.svg`` shipped in the plugin folder."""
    # parents[1] remonte de algorithms/_icons.py à scrutech/ (le dossier du plugin) : le
    # chemin est calculé RELATIVEMENT à ce fichier, jamais en dur, pour marcher quel que
    # soit l'endroit où le plugin est installé sur la machine de l'utilisateur.
    path = Path(__file__).resolve().parents[1] / "icons" / f"{name}.svg"
    return QIcon(str(path))
