"""Run an engine task in the ScruTech Python, without freezing the window.

Same contract as the QGIS plugin: a JSON spec on disk, ``PROGRESS <pct> <msg>`` lines while it
works and one ``RESULT <json>`` line at the end. Here it runs as a QProcess, so the window
stays responsive and Cancel kills the run at once.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from engine_env import ENV_STRIP
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import settings

RUNNER = "vegevigie.qgis_runner"  # the engine entry point both front ends call


class EngineRun(QObject):
    """One engine task: emits progress, log lines, then finished."""

    progress = Signal(int, str)
    message = Signal(str)
    finished = Signal(dict, str)  # payload, error ("" when all went well)

    def __init__(self, python_exe: str, spec: dict, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._payload: dict = {}
        self._buffer = ""
        self._python = python_exe
        self._spec = spec
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._done)
        self.process.errorOccurred.connect(self._failed)

    def start(self) -> None:
        folder = Path(tempfile.mkdtemp(prefix="scrutech_"))
        spec_path = folder / "scrutech_spec.json"
        spec_path.write_text(json.dumps(self._spec), encoding="utf-8")
        self.process.setProcessEnvironment(_environment())
        self.message.emit(f"Calcul lancé : {Path(self._python).name} -m {RUNNER}")
        self.process.start(self._python, ["-m", RUNNER, str(spec_path)])

    def cancel(self) -> None:
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    # --- engine output ---------------------------------------------------------
    def _read(self) -> None:
        chunk = bytes(self.process.readAllStandardOutput().data())  # QByteArray -> bytes
        self._buffer += chunk.decode("utf-8", "replace")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            self._line(line.rstrip("\r"))

    def _line(self, line: str) -> None:
        if line.startswith("PROGRESS "):
            _, _, rest = line.partition(" ")
            pct, _, msg = rest.partition(" ")
            self.progress.emit(int(pct) if pct.isdigit() else -1, msg)
            self.message.emit(msg)
        elif line.startswith("RESULT "):
            self._payload = json.loads(line[len("RESULT ") :])
        elif line.strip():
            self.message.emit(line)

    def _done(self, code: int, _status) -> None:
        if self._buffer.strip():
            self._line(self._buffer.strip())
            self._buffer = ""
        error = self._payload.get("error", "")
        if not error and code != 0 and not self._payload:
            error = f"Le calcul s'est arrêté (code {code}). Le journal ci-dessus dit pourquoi."
        self.finished.emit(self._payload, error)

    def _failed(self, _error) -> None:
        self.finished.emit({}, f"Impossible de lancer le Python de ScruTech : {self._python}")


def _environment() -> QProcessEnvironment:
    """The host environment minus what would break the engine's rasterio/pyproj/GDAL."""
    env = QProcessEnvironment()
    for key, value in os.environ.items():
        if key not in ENV_STRIP:
            env.insert(key, value)
    env.insert("PYTHONIOENCODING", "utf-8")  # accents and arrows in progress messages
    env.insert("SCRUTECH_DATA", str(settings.data_root()))  # one cache, shared with QGIS
    return env
