"""Build the ScruTech plugin and deploy it as a live folder for QGIS — one command.

1. runs ``package.py`` (bundles the engines);
2. copies ``qgis_plugin/scrutech`` -> DEST (default ``~/Desktop/IA/scrutech_plugin``);
3. drops ``venv_path.txt`` pointing at the VegeVigie venv, so the plugin auto-finds the
   interpreter (no path to paste — see algorithms/_venv.py).

Run:  python scrutech/vegevigie/qgis_plugin/deploy_plugin.py [DEST]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent  # qgis_plugin/
PLUGIN_SRC = HERE / "scrutech"
VEGEVIGIE = HERE.parent  # scrutech/vegevigie
DEFAULT_DEST = Path.home() / "Desktop" / "IA" / "scrutech_plugin"
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def _venv_python() -> Path:
    sub = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return VEGEVIGIE / ".venv" / sub


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DEST
    subprocess.run([sys.executable, str(HERE / "package.py")], check=True)

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(PLUGIN_SRC, dest, ignore=_IGNORE)

    py = _venv_python()
    if py.exists():
        (dest / "venv_path.txt").write_text(str(py), encoding="utf-8")
        print(f"venv_path.txt -> {py}")
    else:
        print(f"(no venv at {py} yet — run 'python -m uv sync' in {VEGEVIGIE})")
    print(f"Deployed -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
