"""core.storage offline tests — the layout is the contract, so pin it."""

from pathlib import Path

from core.storage import ENV_ROOT, data_root, db_path, product_path


def test_data_root_honours_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    assert data_root() == tmp_path
    assert db_path() == tmp_path / "scrutech.duckdb"


def test_product_path_layout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    p = product_path("vegevigie", "insee-07005", "trend", "2018_2025", "sen_slope.tif")
    assert p == tmp_path / "vegevigie" / "aoi=insee-07005" / "trend" / "2018_2025" / "sen_slope.tif"


def test_product_path_without_window_or_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    assert product_path("paf", "insee-07005", "interface") == (
        tmp_path / "paf" / "aoi=insee-07005" / "interface"
    )
