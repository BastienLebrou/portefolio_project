"""Find (or create) the external Python that runs the VegeVigie stack — no path to paste.

Resolution order: explicit param > remembered (QgsSettings) > ``venv_path.txt`` dropped
next to the plugin by ``deploy_plugin.py`` > a ``.venv`` beside the engine > create one
with ``uv``. The result is remembered, so it's asked at most once.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_SETTINGS_KEY = "scrutech/vegevigie_python"
HINT_FILE = "venv_path.txt"  # written by deploy_plugin.py next to the plugin


def _python_in(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _settings_get() -> str:
    # QgsSettings est le "stockage de préférences" persistant de QGIS (survit à la
    # fermeture du logiciel, comme les settings d'une appli desktop classique) : on s'en
    # sert ici pour retenir l'interpréteur choisi une fois, afin de ne plus jamais
    # redemander à l'utilisateur au lancement suivant.
    try:
        from qgis.core import QgsSettings

        return QgsSettings().value(_SETTINGS_KEY, "") or ""
    except Exception:  # noqa: BLE001 — outside QGIS or no settings
        return ""


def remember(python_exe: str) -> None:
    """Persist the interpreter so the next run doesn't ask again."""
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
    # a venv bundled with the plugin, or the dev repo's scrutech/vegevigie/.venv
    out.append(str(_python_in(plugin_root / ".venv")))
    out.append(str(_python_in(plugin_root.parents[1] / ".venv")))
    return out


def find_python(plugin_root: Path, explicit: str = "") -> str:
    """Return the first interpreter that exists (explicit wins), or '' if none."""
    ordered = ([explicit] if explicit else []) + _candidates(plugin_root)
    for cand in ordered:
        if cand and Path(cand).exists():
            return cand
    return ""


def provision(project_dir: Path, feedback: object = None) -> str:
    """Create ``project_dir/.venv`` with uv (one-time) and return its python, or ''."""

    def log(msg: str) -> None:
        if feedback is not None:
            feedback.pushInfo(msg)  # type: ignore[attr-defined]

    if not (project_dir / "pyproject.toml").exists():
        log(f"No pyproject at {project_dir} — can't auto-create a venv here.")
        return ""
    log("First run: creating the VegeVigie venv with uv (downloads the stack, ~minutes)…")
    for uv_cmd in ([sys.executable, "-m", "uv"], ["uv"]):
        try:
            proc = subprocess.run(
                [*uv_cmd, "sync", "--project", str(project_dir)],
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except FileNotFoundError:
            continue
        if proc.returncode == 0:
            py = _python_in(project_dir / ".venv")
            if py.exists():
                return str(py)
        log((proc.stderr or proc.stdout or "").strip()[-500:])
        return ""
    log("uv not found — run 'pip install uv' once, or set the Python executable manually.")
    return ""


def resolve(plugin_root: Path, explicit: str, project_dir: Path, feedback: object = None) -> str:
    """Full resolution (find, else provision) + remember the result."""
    found = find_python(plugin_root, explicit)
    if not found:
        found = provision(project_dir, feedback)
    if found:
        remember(found)
    return found
