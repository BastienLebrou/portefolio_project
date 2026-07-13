"""CLI wiring tests: every pipeline stage (M0–M7) is registered on the app."""

from typer.testing import CliRunner

from vegevigie import __version__
from vegevigie.cli import app

runner = CliRunner()

STAGES = ["aoi", "search", "cube", "ndvi", "trend", "drought", "zonal", "dashboard", "run"]


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for stage in STAGES:
        assert stage in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
