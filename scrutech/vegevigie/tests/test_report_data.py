"""Report discovery tests — which pillar outputs are found in a folder, no network."""

from __future__ import annotations

from vegevigie.report.data import discover


def test_discover_empty_folder(tmp_path) -> None:
    data = discover(tmp_path)
    assert not data.any()
    assert data.present() == []


def test_discover_finds_pillar_outputs(tmp_path) -> None:
    (tmp_path / "biotrame_priority.geojson").write_text("{}")
    (tmp_path / "ecobuage_classes.tif").write_bytes(b"")
    (tmp_path / "trend_sen_slope_2018_2022.tif").write_bytes(b"")
    (tmp_path / "alphaearth_change_2018_2023.geojson").write_text("{}")

    data = discover(tmp_path)
    assert data.any()
    assert data.biotrame is not None
    assert data.ecobuage_classes is not None
    assert data.trend is not None
    assert data.alphaearth_change is not None
    present = data.present()
    assert "Biotrame" in present
    assert "Écobuage" in present
    assert "AlphaEarth" in present


def test_discover_scopes_central_store_to_aoi(tmp_path) -> None:
    output = tmp_path / "biotrame" / "aoi=bbox-1" / "output"
    output.mkdir(parents=True)
    (output / "biotrame_priority.geojson").write_text("{}")

    data = discover(tmp_path, "bbox-1")

    assert data.biotrame == output / "biotrame_priority.geojson"


def test_discover_takes_the_latest_run_and_keeps_one_period(tmp_path) -> None:
    import os

    for i, name in enumerate(
        [
            "trend_sen_slope_2018_2020.tif",
            "drought_anomaly_2018_2020.tif",
            "trend_sen_slope_2021_2024.tif",
            "drought_anomaly_2019_2025.tif",
        ]
    ):
        (tmp_path / name).write_bytes(b"")
        os.utime(tmp_path / name, (1_000 + i, 1_000 + i))

    data = discover(tmp_path)

    assert data.trend.name == "trend_sen_slope_2021_2024.tif"
    assert data.drought is None  # never a drought layer from another period than the trend
