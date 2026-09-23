"""Engine output: progress, log and result, read line by line."""

from __future__ import annotations

from scrutech_desktop.engine import EngineRun


def _run() -> EngineRun:
    return EngineRun("python", {"task": "diagnostic"})


def test_progress_result_and_plain_lines_are_sorted_out(qtbot=None) -> None:
    run = _run()
    seen: list = []
    run.progress.connect(lambda pct, msg: seen.append(("progress", pct, msg)))
    run.message.connect(lambda msg: seen.append(("message", msg)))
    run._line("PROGRESS 42 Datacube…")
    run._line('RESULT {"report_path": "C:/r.html"}')
    run._line("un message du moteur")
    assert ("progress", 42, "Datacube…") in seen
    assert ("message", "un message du moteur") in seen
    assert run._payload == {"report_path": "C:/r.html"}


def test_an_engine_error_becomes_the_failure_reason() -> None:
    run = _run()
    errors: list = []
    run.finished.connect(lambda payload, error: errors.append(error))
    run._line('RESULT {"error": "Zone trop grande"}')
    run._done(1, None)
    assert errors == ["Zone trop grande"]


def test_a_crash_without_result_still_explains_itself() -> None:
    run = _run()
    errors: list = []
    run.finished.connect(lambda payload, error: errors.append(error))
    run._done(3, None)
    assert "code 3" in errors[0]
