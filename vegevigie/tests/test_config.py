"""Config loading and validation tests — offline, no network (CLAUDE.md §8)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vegevigie.config import (
    CONFIG_CANDIDATES,
    CONFIG_ENV_VAR,
    Settings,
    default_config_path,
    load_settings,
)


def test_default_config_loads() -> None:
    settings = load_settings()
    assert settings.aoi.departement == "07"
    assert settings.stac.collection == "sentinel-2-l2a"
    assert settings.time.start <= settings.time.end
    assert 0 < settings.trend.p_value < 1
    assert settings.trend.min_valid_months >= 4
    assert settings.composite.fill_max_gap >= 0


def test_default_config_path_exists() -> None:
    assert default_config_path().is_file()


def test_config_candidates_cover_the_three_layouts() -> None:
    """dev repo, bundled QGIS plugin, and packaged wheel — in that order."""
    import vegevigie.config

    here = Path(vegevigie.config.__file__).resolve()
    expected = (
        here.parents[2] / "config" / "default.yaml",  # <repo>/config/default.yaml
        here.parents[1] / "config" / "default.yaml",  # scrutech/config/default.yaml
        here.parent / "default_config.yaml",  # inside the installed package
    )
    assert expected == CONFIG_CANDIDATES


def test_packaged_plugin_layout_resolves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the ScruTech bundle: scrutech/vegevigie/ + scrutech/config/."""
    plugin = tmp_path / "scrutech"
    (plugin / "vegevigie").mkdir(parents=True)
    (plugin / "config").mkdir()
    bundled = plugin / "config" / "default.yaml"
    bundled.write_text((Path(__file__).parents[1] / "config" / "default.yaml").read_text())

    fake_module = plugin / "vegevigie" / "config.py"
    monkeypatch.setattr(
        "vegevigie.config.CONFIG_CANDIDATES",
        (
            fake_module.parents[2] / "config" / "default.yaml",
            fake_module.parents[1] / "config" / "default.yaml",
            fake_module.parent / "default_config.yaml",
        ),
    )
    assert default_config_path() == bundled
    assert load_settings().aoi.departement == "07"


def test_missing_config_names_every_place_it_looked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("vegevigie.config.CONFIG_CANDIDATES", (tmp_path / "nope.yaml",))
    with pytest.raises(FileNotFoundError, match="nope.yaml"):
        default_config_path()


def test_env_var_overrides_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custom = tmp_path / "site.yaml"
    custom.write_text((Path(__file__).parents[1] / "config" / "default.yaml").read_text())
    monkeypatch.setenv(CONFIG_ENV_VAR, str(custom))
    assert default_config_path() == custom

    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "absent.yaml"))
    with pytest.raises(FileNotFoundError, match=CONFIG_ENV_VAR):
        default_config_path()


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
