"""The runner refuses emprises too large for a tool, with a plain-French way out."""

from __future__ import annotations

from vegevigie.qgis_runner import area_problem

ARDECHE = [3.86, 44.26, 4.89, 45.37]  # bbox of the Ardèche, ~10 000 km²
COMMUNE = [5.3195, 45.3215, 5.3669, 45.3573]  # ~15 km²


def test_department_is_refused_but_a_commune_passes() -> None:
    message = area_problem({"task": "paf_interface_aoi", "bbox": ARDECHE})
    assert message is not None and "Zone trop grande" in message and "commune" in message
    assert area_problem({"task": "paf_interface_aoi", "bbox": COMMUNE}) is None


def test_vegevigie_limit_follows_pixels_and_period() -> None:
    commune_10m = {"bbox": COMMUNE, "start": 2021, "end": 2024, "resolution": 10}
    assert area_problem(commune_10m) is None  # ~6 M pixel-months
    assert area_problem({**commune_10m, "start": 2000}) is not None  # 25 years at 10 m
    assert area_problem({**commune_10m, "bbox": ARDECHE, "resolution": 60}) is not None


def test_tasks_without_a_limit_are_not_checked() -> None:
    assert area_problem({"task": "alphaearth_change", "bbox": ARDECHE}) is None
    assert area_problem({"task": "report", "bbox": ARDECHE}) is None
