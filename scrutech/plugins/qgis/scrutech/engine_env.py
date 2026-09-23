"""Build, check and locate the ScruTech engine environment (pure stdlib, no QGIS, no GUI).

The heavy stack (datacube, GeoPandas, DuckDB, Earth Engine…) never goes into the host
application's Python: pip-installed GDAL-based packages clash with QGIS's GDAL, and the
desktop app has no use for them either. Instead ``uv`` builds a separate environment in
``~/.scrutech/venv`` from the engine sources and ``uv.lock``, and both front ends (the QGIS
plugin and the ScruTech desktop app) call into it as a subprocess. This module is that shared
plumbing: find or download uv, install the environment, check it, handle the Earth Engine key.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

# The host application sets these to its own runtime; they must NOT leak into the engine
# interpreter or they break its rasterio/pyproj/GDAL.
ENV_STRIP = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "GDAL_DATA",
    "GDAL_DRIVER_PATH",
    "PROJ_LIB",
    "PROJ_DATA",
    "GEOTIFF_CSV",
)

USER_VENV = Path.home() / ".scrutech" / "venv"
# Where AlphaEarth and the setup check look for the Google Earth Engine key by default.
DEFAULT_GEE_KEY = Path.home() / ".scrutech" / "gee_key.json"
# Measured on the reference install (uv sync --no-dev, without the optional GeoAI extra).
ENV_SIZE = "environ 1 Go"
# uv is fetched here when missing: the user's own folder, no admin rights, PATH untouched.
UV_HOME = Path.home() / ".scrutech" / "bin"
# Pinned to the uv that wrote uv.lock, so an install never meets a newer lock format.
UV_VERSION = "0.12.13"
_UV_RELEASES = "https://github.com/astral-sh/uv/releases/download"

UV_MISSING = (
    "Le programme « uv » (installateur Python gratuit, édité par Astral) n'a pas pu être "
    "téléchargé automatiquement ({error}).\n"
    "1. Ouvrez PowerShell (menu Démarrer) et collez cette ligne :\n"
    '   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"\n'
    "   (macOS ou Linux : curl -LsSf https://astral.sh/uv/install.sh | sh)\n"
    "2. Relancez cet outil. Si uv reste introuvable, indiquez son chemin dans les paramètres "
    "avancés (souvent %USERPROFILE%\\.local\\bin\\uv.exe)."
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
        "rasterio", "geopandas", "duckdb", "h3", "ee", "folium"]
print(json.dumps({"python": sys.version.split()[0], "missing": [m for m in mods if not found(m)],
                  "geoai": found("samgeo")}))
"""
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ENV_STRIP}


def find_uv() -> str:
    """``uv`` on PATH, else where its official installers put it ('' if absent).

    QGIS on Windows starts with its own PATH, so a PATH lookup alone often misses uv.
    """
    exe = _uv_exe()
    home = Path.home()
    for cand in (
        shutil.which("uv"),
        UV_HOME / exe,
        home / ".local" / "bin" / exe,
        home / ".cargo" / "bin" / exe,
    ):
        if cand and Path(cand).is_file():
            return str(cand)
    return ""


def _uv_exe() -> str:
    return "uv.exe" if os.name == "nt" else "uv"


def uv_asset() -> str:
    """The official uv release archive for this machine."""
    import platform
    import sys

    arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
    if os.name == "nt":
        return f"uv-{arch}-pc-windows-msvc.zip"
    if sys.platform == "darwin":
        return f"uv-{arch}-apple-darwin.tar.gz"
    return f"uv-{arch}-unknown-linux-gnu.tar.gz"


def download_uv(log: Callable[[str], None]) -> str:
    """Fetch the pinned official uv into :data:`UV_HOME` and return its path.

    A single ~20 MB archive from Astral's GitHub releases, over HTTPS: no installer script,
    no admin rights, nothing added to PATH. Raises OSError on network or archive problems.
    """
    import io
    import tarfile
    import urllib.request
    import zipfile

    asset = uv_asset()
    url = f"{_UV_RELEASES}/{UV_VERSION}/{asset}"
    log(f"Téléchargement de uv {UV_VERSION} (installateur Python, environ 20 Mo) : {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 — fixed https URL
        data = resp.read()
    exe = _uv_exe()
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist() if n.rsplit("/", 1)[-1] == exe]
            if not names:
                raise OSError(f"{exe} absent de l'archive {asset}")
            binary = archive.read(names[0])
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = [m for m in archive.getmembers() if m.name.rsplit("/", 1)[-1] == exe]
            handle = archive.extractfile(members[0]) if members else None
            if handle is None:
                raise OSError(f"{exe} absent de l'archive {asset}")
            binary = handle.read()
    UV_HOME.mkdir(parents=True, exist_ok=True)
    target = UV_HOME / exe
    target.write_bytes(binary)
    target.chmod(0o755)
    log(f"uv installé : {target}")
    return str(target)


def engine_project(plugin_root: Path) -> Path | None:
    """The ``vegevigie`` project to build from: bundled in the ZIP, else the dev repo."""
    dev = plugin_root.parents[2] / "packages" / "vegevigie"  # scrutech/plugins/qgis/scrutech
    for cand in (plugin_root / "engine" / "vegevigie", dev):
        if (cand / "pyproject.toml").is_file() and (cand / "uv.lock").is_file():
            return cand
    return None


def install_env(
    uv: str,
    project: Path,
    log: Callable[[str], None],
    canceled: Callable[[], bool],
    geoai: bool = False,
) -> int:
    """``uv sync`` the engine into :data:`USER_VENV`, streaming uv's output. -1 if canceled.

    Minimal by default; ``geoai`` adds the optional Segment Anything stack (torch).
    """
    env = _clean_env()
    env["UV_PROJECT_ENVIRONMENT"] = str(USER_VENV)
    # uv's own Python only: a Microsoft Store "python" alias (WindowsApps), a conda or a pyenv
    # shim on the user's machine gives a venv that cannot start ("No Python at ...").
    env["UV_PYTHON_PREFERENCE"] = "only-managed"
    # Pinned: uv would otherwise pick any Python >= 3.11 on the machine, and some locked
    # wheels (numcodecs…) do not exist for the newest one. uv downloads 3.11 if needed.
    cmd = [uv, "sync", "--frozen", "--no-dev", "--python", "3.11", "--project", str(project)]
    if geoai:
        cmd += ["--extra", "geoai"]
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


def install_problem(log: str) -> str:
    """The line of a failed setup run's log worth showing in QGIS's message bar.

    A « [À FAIRE] » line if the check wrote one; else the error the run ended on, read from
    the bottom and skipping its numbered steps and indented commands to reach its headline.
    """
    lines = [line for line in log.splitlines() if line.strip()]
    todo = [line.strip() for line in lines if "À FAIRE" in line]
    if todo:
        return todo[0][:220]
    for line in reversed(lines):
        if not line[0].isspace() and not line.split(".", 1)[0].isdigit():
            return line.strip()[:220]
    return "raison inconnue"


def save_gee_key(key_text: str) -> Path | None:
    """Store a valid key at :data:`DEFAULT_GEE_KEY`, where AlphaEarth finds it on its own.

    Returns where it went (None if that very key was already there). A different key already
    in place is kept next to it as ``gee_key.json.bak`` rather than lost.
    """
    target = DEFAULT_GEE_KEY
    if target.is_file():
        if target.read_text(encoding="utf-8") == key_text:
            return None
        target.replace(target.with_name(target.name + ".bak"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(key_text, encoding="utf-8")
    return target


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
