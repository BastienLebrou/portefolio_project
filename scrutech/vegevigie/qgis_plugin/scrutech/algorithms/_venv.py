"""Find the external Python that runs the ScruTech engines: no path to paste.

Resolution order: explicit parameter > remembered (QgsSettings) > ``venv_path.txt`` dropped
next to the plugin by ``deploy_plugin.py`` > the dev repo's ``scrutech/vegevigie/.venv`` >
``~/.scrutech/venv`` built by « Vérifier et installer ScruTech ». Nothing is created here:
installing downloads about 1 GB, so only the setup tool does it, when the user asks.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._setup import ENV_SIZE, USER_VENV

_SETTINGS_KEY = "scrutech/vegevigie_python"
HINT_FILE = "venv_path.txt"  # written by deploy_plugin.py next to the plugin
PYTHON_LABEL = "Python de ScruTech (laisser vide : détection automatique)"
MISSING_ENV = (
    "Le Python de ScruTech n'est pas installé. Ouvrez « 0 · Démarrer ici ▸ Vérifier et "
    "installer ScruTech », cochez « Installer ou mettre à jour » puis Exécuter (une seule "
    f"fois, {ENV_SIZE}). Relancez ensuite cet outil."
)


def _python_in(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _settings_get() -> str:
    try:
        from qgis.core import QgsSettings

        return QgsSettings().value(_SETTINGS_KEY, "") or ""
    except Exception:  # noqa: BLE001 — outside QGIS or no settings
        return ""


def remember(python_exe: str) -> None:
    """Persist the interpreter so the next run finds it at once."""
    try:
        from qgis.core import QgsSettings

        QgsSettings().setValue(_SETTINGS_KEY, python_exe)
    except Exception:  # noqa: BLE001
        pass


def _candidates(plugin_root: Path) -> list[str]:
    """Ordered interpreter guesses (most specific first)."""
    out: list[str] = []
    remembered = _settings_get()
    if remembered:
        out.append(remembered)
    hint = plugin_root / HINT_FILE
    if hint.exists():
        out.append(hint.read_text(encoding="utf-8").strip())
    out.append(str(_python_in(plugin_root.parents[1] / ".venv")))  # dev: scrutech/vegevigie
    out.append(str(_python_in(USER_VENV)))
    return out


def find_python(plugin_root: Path, explicit: str = "") -> str:
    """Return the first interpreter that exists (explicit wins), or '' if none."""
    ordered = ([explicit] if explicit else []) + _candidates(plugin_root)
    for cand in ordered:
        if cand and Path(cand).is_file():
            return cand
    return ""


def python_param(name: str):
    """The optional « Python de ScruTech » parameter every engine tool shares (advanced)."""
    from qgis.core import QgsProcessingParameterFile

    from . import _qgis_compat as compat

    return compat.advanced(
        QgsProcessingParameterFile(
            name, PYTHON_LABEL, behavior=compat.FILE_BEHAVIOR_FILE, optional=True
        )
    )


def require_python(explicit: str, feedback) -> str:
    """The interpreter to run an engine in, else a QgsProcessingException saying what to do."""
    from qgis.core import QgsProcessingException

    python_exe = find_python(Path(__file__).resolve().parents[1], explicit)
    if not python_exe:
        raise QgsProcessingException(MISSING_ENV)
    remember(python_exe)
    feedback.pushInfo(f"Python de ScruTech : {python_exe}")
    return python_exe
