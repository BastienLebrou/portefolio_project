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
    assert "AlphaEarth (changement)" in present
