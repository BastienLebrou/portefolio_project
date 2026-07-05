"""Config loading and validation tests — offline, no network (CLAUDE.md §8)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vegevigie.config import DEFAULT_CONFIG_PATH, Settings, load_settings


def test_default_config_loads() -> None:
    settings = load_settings()
    assert settings.aoi.departement == "07"
    assert settings.stac.collection == "sentinel-2-l2a"
    assert settings.time.start <= settings.time.end
    assert 0 < settings.trend.p_value < 1


def test_default_config_path_exists() -> None:
    assert DEFAULT_CONFIG_PATH.is_file()


def test_paths_derived_dirs() -> None:
    settings = load_settings()
    data_dir = settings.paths.data_dir
    assert settings.paths.raw == data_dir / "raw"
    assert settings.paths.interim == data_dir / "interim"
    assert settings.paths.processed == data_dir / "processed"


def test_small_bbox_is_valid_wgs84() -> None:
    min_lon, min_lat, max_lon, max_lat = load_settings().aoi.small_bbox
    assert -180 <= min_lon < max_lon <= 180
    assert -90 <= min_lat < max_lat <= 90


def _base_config() -> dict:
    return load_settings().model_dump()


def test_reversed_time_window_rejected() -> None:
    raw = _base_config()
    raw["time"] = {"start": 2025, "end": 2018}
    with pytest.raises(ValidationError, match="must be >="):
        Settings.model_validate(raw)


def test_cloud_cover_out_of_range_rejected() -> None:
    raw = _base_config()
    raw["stac"]["max_cloud_cover"] = 150
    with pytest.raises(ValidationError):
        Settings.model_validate(raw)


def test_load_settings_custom_path(tmp_path: Path) -> None:
    custom = tmp_path / "custom.yaml"
    raw = _base_config()
    raw["raster"]["resolution"] = 10
    raw["paths"]["data_dir"] = str(raw["paths"]["data_dir"])

    import yaml

    custom.write_text(yaml.safe_dump(raw))
    assert load_settings(custom).raster.resolution == 10
