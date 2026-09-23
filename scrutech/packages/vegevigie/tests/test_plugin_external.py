"""External engine runs (no QGIS needed): Cancel must stop a silent engine at once."""

import sys
import time
from pathlib import Path

import pytest
from scrutech.algorithms import _external  # noqa: E402


class _CancelAfter:
    """A Processing feedback whose user clicks Cancel after ``delay`` seconds."""

    def __init__(self, delay: float) -> None:
        self.deadline = time.monotonic() + delay

    def isCanceled(self) -> bool:  # noqa: N802 — QGIS API name
        return time.monotonic() > self.deadline

    def pushInfo(self, _message: str) -> None:  # noqa: N802
        pass

    def setProgress(self, _pct: int) -> None:  # noqa: N802
        pass


def test_progress_and_result_are_read_from_the_engine(tmp_path: Path) -> None:
    engine = 'print("PROGRESS 40 Moitié")\nprint(\'RESULT {"path": "a.tif"}\')\n'
    (tmp_path / "chatty_engine.py").write_text(engine, encoding="utf-8")
    feedback = _CancelAfter(60)

    payload = _external.run_spec(
        sys.executable, "chatty_engine", {}, tmp_path, feedback, {"PYTHONPATH": str(tmp_path)}
    )

    assert payload == {"path": "a.tif"}


def test_non_latin_progress_does_not_kill_the_engine(tmp_path: Path, monkeypatch) -> None:
    # A cp1252 console (Windows outside QGIS's UTF-8 launcher) cannot encode "→": the engine
    # died on it with a 'charmap' error. The pipe must be UTF-8 on both ends.
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    engine = 'print("PROGRESS 80 Axes → score…")\nprint(\'RESULT {"ok": "é→"}\')\n'
    (tmp_path / "arrow_engine.py").write_text(engine, encoding="utf-8")

    payload = _external.run_spec(
        sys.executable,
        "arrow_engine",
        {},
        tmp_path,
        _CancelAfter(60),
        {"PYTHONPATH": str(tmp_path)},
    )

    assert payload == {"ok": "é→"}


def test_cancel_stops_an_engine_that_prints_nothing(tmp_path: Path) -> None:
    (tmp_path / "silent_engine.py").write_text("import time\ntime.sleep(20)\n")
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="Annulé"):
        _external.run_spec(
            sys.executable,
            "silent_engine",
            {},
            tmp_path,
            _CancelAfter(0.5),
            extra_env={"PYTHONPATH": str(tmp_path)},
        )

    assert time.monotonic() - started < 5
