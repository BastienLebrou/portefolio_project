"""qgis_runner tests — spec dispatch + line protocol, offline (§8).

The heavy engine calls are monkeypatched: these tests pin the *contract* the
ScruTech plugin parses (PROGRESS / HEARTBEAT / RESULT lines, stage routing),
not the science.
"""

import json
import time
from pathlib import Path
from typing import Any

import pytest

from vegevigie import qgis_runner, stages
from vegevigie.pipeline import PipelineResult, build_settings
from vegevigie.stages import RunManifest, StageOutcome


def _write_spec(tmp_path: Path, **body: Any) -> Path:
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(body))
    return spec


def _result_line(out: str) -> dict[str, Any]:
    last = out.strip().splitlines()[-1]
    assert last.startswith("RESULT "), out
    return json.loads(last.removeprefix("RESULT "))


def test_no_spec_is_an_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert qgis_runner.main([]) == 2
    assert '"error"' in capsys.readouterr().out


def test_missing_manifest_reports_error_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _write_spec(tmp_path, stage="trend", out_folder=str(tmp_path), heartbeat=999)
    assert qgis_runner.main([str(spec)]) == 1
    result = _result_line(capsys.readouterr().out)
    assert "scrutech_run.json" in result["error"]
    assert result["stage"] == "trend"


def test_single_stage_dispatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings((0.0, 0.0, 1.0, 1.0), 2020, 2020, data_dir=tmp_path)
    RunManifest.for_settings(settings).save()  # downstream stages read the manifest

    def fake_run_stage(stage: str, _settings: Any, **kwargs: Any) -> StageOutcome:
        kwargs["progress"](50, "halfway")
        return StageOutcome(stage, {"sen_slope": tmp_path / "trend.tif"}, {"months": 12})

    monkeypatch.setattr(stages, "run_stage", fake_run_stage)
    spec = _write_spec(tmp_path, stage="trend", out_folder=str(tmp_path), heartbeat=999)
    assert qgis_runner.main([str(spec)]) == 0

    lines = capsys.readouterr().out.strip().splitlines()
    assert "PROGRESS 50 halfway" in lines
    result = json.loads(lines[-1].removeprefix("RESULT "))
    assert result["stage"] == "trend"
    assert not result["skipped"]
    assert result["artifacts"]["sen_slope"].endswith("trend.tif")
    assert result["meta"]["months"] == 12


def test_all_dispatch_uses_pipeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from vegevigie import pipeline

    def fake_run_pipeline(settings: Any, **kwargs: Any) -> PipelineResult:
        kwargs["progress"](10, "searching")
        result = PipelineResult(settings=settings)
        result.scene_count = 3
        result.trend_tif = tmp_path / "trend.tif"
        result.trend_class_tif = tmp_path / "trend_class.tif"
        return result

    monkeypatch.setattr(pipeline, "run_pipeline", fake_run_pipeline)
    spec = _write_spec(
        tmp_path,
        out_folder=str(tmp_path),
        bbox=[0.0, 0.0, 1.0, 1.0],
        start=2020,
        end=2020,
        heartbeat=999,
    )
    assert qgis_runner.main([str(spec)]) == 0

    out = capsys.readouterr().out
    assert "PROGRESS 10 searching" in out
    result = _result_line(out)
    assert result["stage"] == "all"
    assert result["scene_count"] == 3
    assert result["trend_tif"].endswith("trend.tif")
    assert result["trend_class_tif"].endswith("trend_class.tif")
    assert result["zonal_gpkg"] is None


def test_heartbeat_emits_lines(capfd: pytest.CaptureFixture[str]) -> None:
    with qgis_runner._Heartbeat(0.02):
        time.sleep(0.08)
    assert "HEARTBEAT" in capfd.readouterr().out
