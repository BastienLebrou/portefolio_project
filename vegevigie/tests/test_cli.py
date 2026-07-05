"""CLI wiring tests: every pipeline stage is registered and behaves as an M0 stub."""

import pytest
from typer.testing import CliRunner

from vegevigie import __version__
from vegevigie.cli import app

runner = CliRunner()

STAGES = ["aoi", "search", "cube", "ndvi", "trend", "drought", "zonal", "dashboard", "run"]
# Stages still awaiting implementation; aoi/search (M1), cube/ndvi (M2/M3),
# trend (M4) landed.
STUB_STAGES = ["drought", "zonal", "dashboard", "run"]


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for stage in STAGES:
        assert stage in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize("stage", STUB_STAGES)
def test_stub_stages_report_milestone(stage: str) -> None:
    result = runner.invoke(app, [stage])
    assert result.exit_code == 1
    assert "not implemented yet" in result.output
