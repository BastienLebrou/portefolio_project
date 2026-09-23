"""The library and its specs: what a tile promises is what the engine receives."""

from __future__ import annotations

from pathlib import Path

from scrutech_desktop.catalog import APPLICATIONS, BY_KEY
from scrutech_desktop.icons import ASSETS

BBOX = (5.31, 45.32, 5.36, 45.35)


def test_every_application_is_unique_and_has_its_icon() -> None:
    assert len(BY_KEY) == len(APPLICATIONS)
    for app in APPLICATIONS:
        assert (ASSETS / f"{app.icon}.svg").is_file(), app.key
        assert app.name and app.tagline.endswith(".")


def test_the_form_values_become_the_engine_spec() -> None:
    diagnostic = BY_KEY["diagnostic"]
    spec = diagnostic.spec(BBOX, {"start": 2020, "end": 2025, "resolution": 30}, "C:/runs/d")
    assert spec == {
        "task": "diagnostic",
        "bbox": list(BBOX),
        "start": 2020,
        "end": 2025,
        "resolution": 30,
        "out_folder": "C:/runs/d",
    }


def test_a_raster_application_writes_to_a_file_not_a_folder() -> None:
    spec = BY_KEY["mnt"].spec(BBOX, {"resolution": 5.0}, "C:/runs/mnt/sortie.tif")
    assert spec["out_path"] == "C:/runs/mnt/sortie.tif" and "out_folder" not in spec


def test_choice_fields_offer_their_default() -> None:
    hexagons = next(f for f in BY_KEY["biotrame"].fields if f.key == "hexagons")
    assert hexagons.default in [value for _label, value in hexagons.choices]


def test_the_engine_entry_point_is_the_one_the_plugin_uses() -> None:
    from scrutech_desktop.engine import RUNNER

    runner = Path(__file__).resolve().parents[2] / "packages" / "vegevigie" / "src"
    assert (runner / RUNNER.replace(".", "/")).with_suffix(".py").is_file()
