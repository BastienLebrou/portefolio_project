"""What ScruTech remembers between sessions, and where it keeps the analyses.

Only three things: the engine Python, the data folder and the last extent. Everything else
(the Earth Engine key, the engine itself) lives in ``~/.scrutech``, shared with the QGIS
plugin, so a user configures ScruTech once for both.
"""

from __future__ import annotations

import os
from pathlib import Path

from engine_env import USER_VENV
from PySide6.QtCore import QSettings

_SETTINGS = QSettings("ScruTech", "ScruTech")
_PYTHON = "engine/python"
_DATA = "engine/data_root"
_EXTENT = "map/extent"
DEFAULT_DATA_ROOT = Path.home() / ".scrutech" / "data"


def engine_python() -> str:
    """The engine interpreter: the chosen one, the installed one, else the repo's own venv."""
    chosen = str(_SETTINGS.value(_PYTHON, "") or "")
    if chosen and Path(chosen).is_file():
        return chosen
    inside = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    # In development the app runs from the repo, where vegevigie already has its venv.
    repo = Path(__file__).resolve().parents[3] / "packages" / "vegevigie" / ".venv"
    for venv in (USER_VENV, repo):
        if (venv / inside).is_file():
            return str(venv / inside)
    return ""


def set_engine_python(path: str) -> None:
    _SETTINGS.setValue(_PYTHON, path)


def data_root() -> Path:
    return Path(str(_SETTINGS.value(_DATA, "") or DEFAULT_DATA_ROOT))


def set_data_root(path: str | Path) -> None:
    _SETTINGS.setValue(_DATA, str(path))


def last_extent() -> tuple[float, float, float, float] | None:
    saved = _SETTINGS.value(_EXTENT, "")
    try:
        west, south, east, north = (float(v) for v in str(saved).split(","))
    except ValueError:
        return None
    return west, south, east, north


def set_last_extent(bbox: tuple[float, float, float, float]) -> None:
    _SETTINGS.setValue(_EXTENT, ",".join(f"{v:.5f}" for v in bbox))


def run_folder(app_key: str, bbox: tuple[float, float, float, float]) -> Path:
    """Where a run writes: one folder per zone and application, under the data folder."""
    zone = "_".join(f"{v:.4f}" for v in bbox)
    return data_root() / "runs" / f"zone-{zone}" / app_key
