"""Run a heavy ScruTech engine in an external Python interpreter.

The pillars that need GeoPandas / requests / DuckDB (SDBPi, mini data centers) can't
run in QGIS's bundled Python. Rather than pollute it, ScruTech shells out to a venv
that has the stack — the same pattern as the VegeVigie ``analyze_extent`` algorithm.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

# QGIS sets these to its own runtime; they must NOT leak into an external interpreter
# or they break its rasterio/pyproj/GDAL.
_ENV_STRIP = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "GDAL_DATA",
    "GDAL_DRIVER_PATH",
    "PROJ_LIB",
    "PROJ_DATA",
    "GEOTIFF_CSV",
)


def run_engine(python_exe: str, script: Path, args: list[str], feedback) -> int:
    """Run ``[python_exe, script, *args]`` with a QGIS-safe env, streaming stdout.

    Returns the process exit code (-1 if the user cancelled).
    """
    cmd = [python_exe, str(script), *args]
    feedback.pushInfo("Running engine in external interpreter:\n  " + " ".join(cmd))
    env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        creationflags=creationflags,
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        if feedback.isCanceled():
            proc.terminate()
            return -1
        line = raw.rstrip("\n")
        if line:
            feedback.pushInfo(line)
    proc.wait()
    return proc.returncode
