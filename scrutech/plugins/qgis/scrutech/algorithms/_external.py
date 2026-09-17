"""Run a heavy ScruTech engine in an external Python interpreter.

The engines need GeoPandas / rasterio / DuckDB, which QGIS's bundled Python lacks (and
installing them there clashes with QGIS's own GDAL). ScruTech shells out instead to the
separate Python built by « Vérifier et installer ScruTech ».
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import subprocess
import threading
from collections.abc import Callable
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


def _stream(cmd: list[str], env: dict, feedback, on_line: Callable[[str], None]) -> int:
    """Run ``cmd``, hand each output line to ``on_line``, return the exit code.

    The output is read in a thread so Cancel works even while the engine prints nothing for
    minutes (a datacube load): the process is killed at once and RuntimeError("Annulé.") raised.
    """
    with subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as proc:
        lines: queue.Queue[str | None] = queue.Queue()

        def pump() -> None:
            with contextlib.suppress(ValueError, OSError):  # pipe closed by a cancel
                for raw in proc.stdout or ():
                    lines.put(raw.rstrip("\n"))
            lines.put(None)

        threading.Thread(target=pump, daemon=True).start()
        while True:
            if feedback.isCanceled():
                proc.kill()
                raise RuntimeError("Annulé.")
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if line is None:
                break
            on_line(line)
    return proc.returncode


def run_engine(python_exe: str, script: Path, args: list[str], feedback) -> int:
    """Run ``[python_exe, script, *args]`` with a QGIS-safe env, streaming stdout.

    Returns the process exit code (-1 if the user cancelled).
    """
    cmd = [python_exe, str(script), *args]
    feedback.pushInfo("Calcul lancé dans le Python de ScruTech :\n  " + " ".join(cmd))
    env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
    try:
        return _stream(cmd, env, feedback, lambda line: line and feedback.pushInfo(line))
    except RuntimeError:
        return -1


def run_spec(
    python_exe: str,
    module: str,
    spec: dict,
    out_folder: Path,
    feedback,
    extra_env: dict | None = None,
) -> dict:
    """Write ``spec`` to JSON, run ``python -m module spec.json``, parse PROGRESS/RESULT.

    Shared by every area-of-interest tool. Streams ``PROGRESS <pct> <msg>`` to the feedback
    and returns the ``RESULT <json>`` payload. ``extra_env`` injects secrets (e.g. GEE
    credentials) into the child env only — never written to the spec on disk.
    Raises RuntimeError with a readable message on engine error, non-zero exit or cancel.
    """
    out_folder.mkdir(parents=True, exist_ok=True)
    spec_path = out_folder / "scrutech_spec.json"
    spec_path.write_text(json.dumps(spec))

    cmd = [python_exe, "-m", module, str(spec_path)]
    feedback.pushInfo("Calcul lancé dans le Python de ScruTech :\n  " + " ".join(cmd))
    env = {k: v for k, v in os.environ.items() if k not in _ENV_STRIP}
    if extra_env:
        env.update(extra_env)
    payload: dict = {}

    def on_line(line: str) -> None:
        if line.startswith("PROGRESS "):
            # "PROGRESS 42 Building datacube..." -> on découpe sur les ESPACES, mais
            # seulement les deux premiers : partition(" ") coupe au premier espace
            # rencontré et renvoie (avant, séparateur, après) ; on l'appelle deux fois
            # pour extraire d'abord le mot "PROGRESS", puis séparer le pourcentage du
            # message (qui, lui, peut contenir des espaces sans être redécoupé).
            _, _, rest = line.partition(" ")
            pct, _, msg = rest.partition(" ")
            with contextlib.suppress(ValueError):
                feedback.setProgress(int(pct))
            feedback.pushInfo(msg)
        elif line.startswith("RESULT "):
            payload.update(json.loads(line[len("RESULT ") :]))
        elif line:
            feedback.pushInfo(line)

    returncode = _stream(cmd, env, feedback, on_line)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    if returncode != 0 and not payload:
        raise RuntimeError(
            f"Le calcul a échoué (code {returncode}). Le journal ci-dessus indique pourquoi."
        )
    return payload
