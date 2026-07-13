"""Engine-API tests — the offline parts of pipeline.py (build_settings), no network."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from vegevigie.pipeline import build_settings


def test_build_settings_overrides_bbox_and_window() -> None:
    bbox = (4.5, 44.5, 4.7, 44.6)
    s = build_settings(bbox, 2019, 2021, resolution=20, max_cloud_cover=30)
    assert s.aoi.small_bbox == bbox
    assert (s.time.start, s.time.end) == (2019, 2021)
    assert s.raster.resolution == 20
    assert s.stac.max_cloud_cover == 30


def test_build_settings_defaults_preserved() -> None:
    s = build_settings((0.0, 0.0, 1.0, 1.0), 2020, 2020)
    # Untouched fields fall back to config/default.yaml.
    assert s.stac.collection == "sentinel-2-l2a"
    assert s.trend.p_value == 0.05


def test_build_settings_custom_data_dir(tmp_path: Path) -> None:
    s = build_settings((0.0, 0.0, 1.0, 1.0), 2020, 2020, data_dir=tmp_path / "out")
    assert s.paths.data_dir == tmp_path / "out"
    assert s.paths.processed == tmp_path / "out" / "processed"


def test_build_settings_rejects_bad_window() -> None:
    with pytest.raises(ValidationError):
        build_settings((0.0, 0.0, 1.0, 1.0), 2022, 2019)  # end < start
