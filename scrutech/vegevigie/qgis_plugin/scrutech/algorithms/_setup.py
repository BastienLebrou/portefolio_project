"""Build and check the external Python that runs the ScruTech engines (no QGIS import).

The heavy stack (datacube, GeoPandas, DuckDB, Earth Engine…) never goes into QGIS's own
Python: pip-installed GDAL-based packages clash with QGIS's GDAL. Instead ``uv`` builds a
separate environment in ``~/.scrutech/venv`` from the engine sources and ``uv.lock`` that
``package.py`` ships inside the plugin, so every user gets the versions the tests ran with.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from ._external import _ENV_STRIP

USER_VENV = Path.home() / ".scrutech" / "venv"
# Where AlphaEarth and the setup check look for the Google Earth Engine key by default.
DEFAULT_GEE_KEY = Path.home() / ".scrutech" / "gee_key.json"
# Measured on the reference install (uv sync --no-dev, without the optional GeoAI extra).
ENV_SIZE = "environ 1 Go"

UV_MISSING = (
    "Le programme « uv » (installateur Python gratuit, édité par Astral) est introuvable.\n"
    "1. Ouvrez PowerShell (menu Démarrer) et collez cette ligne :\n"
    '   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"\n'
    "   (macOS ou Linux : curl -LsSf https://astral.sh/uv/install.sh | sh)\n"
    "2. Redémarrez QGIS et relancez cet outil. Si uv reste introuvable, indiquez son chemin "
    "dans les paramètres avancés (souvent %USERPROFILE%\\.local\\bin\\uv.exe)."
)

# Run inside the external Python: find_spec only locates modules, nothing is executed.
_CHECK_SCRIPT = """
import importlib.util, json, sys
def found(name):
    try:
        return importlib.util.find_spec(name) is not None
    except ImportError:
        return False
mods = ["vegevigie", "core", "biotrame", "alphaearth", "ecobuage", "odc.stac", "xarray",
        "rasterio", "geopandas", "duckdb", "h3", "ee", "streamlit"]
print(json.dumps({"python": sys.version.split()[0], "missing": [m for m in mods if not found(m)],
                  "geoai": found("samgeo")}))
"""
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}


def find_uv() -> str:
    """``uv`` on PATH, else where its official installers put it ('' if absent).

    QGIS on Windows starts with its own PATH, so a PATH lookup alone often misses uv.
    """
    exe = "uv.exe" if os.name == "nt" else "uv"
    home = Path.home()
    for cand in (shutil.which("uv"), home / ".local" / "bin" / exe, home / ".cargo" / "bin" / exe):
        if cand and Path(cand).is_file():
            return str(cand)
    return ""


def engine_project(plugin_root: Path) -> Path | None:
    """The ``vegevigie`` project to build from: bundled in the ZIP, else the dev repo."""
    for cand in (plugin_root / "engine" / "vegevigie", plugin_root.parents[1]):
        if (cand / "pyproject.toml").is_file() and (cand / "uv.lock").is_file():
            return cand
    return None


def install_env(
    uv: str, project: Path, log: Callable[[str], None], canceled: Callable[[], bool]
) -> int:
    """``uv sync`` the engine into :data:`USER_VENV`, streaming uv's output. -1 if canceled."""
    env = _clean_env()
    env["UV_PROJECT_ENVIRONMENT"] = str(USER_VENV)
    cmd = [uv, "sync", "--frozen", "--no-dev", "--project", str(project)]
    log("Commande : " + " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
        creationflags=_NO_WINDOW,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        if canceled():
            proc.terminate()
            return -1
        if line.strip():
            log(line.rstrip())
    return proc.wait()


def check_env(python_exe: str) -> dict:
    """What the external Python can import: ``{python, missing, geoai}``, or ``{error}``."""
    try:
        out = subprocess.run(
            [python_exe, "-c", _CHECK_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=_clean_env(),
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": str(exc)}
    try:
        return json.loads(out.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"error": (out.stderr or out.stdout).strip()[-300:] or f"code {out.returncode}"}


def check_gee_key(text: str) -> list[str]:
    """Problems with a Google Earth Engine service-account key, in plain French ([] = OK)."""
    try:
        key = json.loads(text)
    except ValueError:
        return ["le fichier n'est pas un JSON valide"]
    if not isinstance(key, dict):
        return ["le fichier n'est pas une clé de compte de service"]
    problems = []
    if key.get("type") != "service_account":
        problems.append("ce n'est pas une clé de compte de service (type ≠ service_account)")
    fields = ("client_email", "private_key", "project_id")
    problems += [f"champ « {name} » manquant" for name in fields if not key.get(name)]
    return problems


# Run inside the external Python: authenticates and makes one tiny computation, so a missing
# Google Cloud permission shows up here rather than in the middle of an analysis.
_GEE_SCRIPT = """
import json, os, ee
creds = json.loads(os.environ["SCRUTECH_GEE_CREDENTIALS"])
ee.Initialize(
    credentials=ee.ServiceAccountCredentials(creds["client_email"], key_data=json.dumps(creds)),
    project=creds.get("project_id"),
)
ee.Number(1).getInfo()
print("GEE_OK")
"""


def check_gee_access(python_exe: str, key_text: str) -> str:
    """'' if Earth Engine accepts the key for a real request, else the error message."""
    env = _clean_env()
    env["SCRUTECH_GEE_CREDENTIALS"] = json.dumps(json.loads(key_text))
    try:
        out = subprocess.run(
            [python_exe, "-c", _GEE_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env=env,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if "GEE_OK" in out.stdout:
        return ""
    lines = (out.stderr or out.stdout).strip().splitlines()
    return lines[-1] if lines else f"code {out.returncode}"
