"""Climate projection: TRACC anchoring, regression, exposure maths, Open-Meteo cache (offline)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from vegevigie import projection as pj


def _daily(models=("A", "B")) -> pd.DataFrame:
    """2000-2050 days warming 0.04 °C/year, summers crossing 30 °C more and more often."""
    time = pd.date_range("2000-01-01", "2050-12-31", freq="D")
    years = time.year.to_numpy() - 2000
    season = 12 * np.sin(2 * np.pi * (time.dayofyear.to_numpy() - 110) / 365)
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"time": time})
    for i, model in enumerate(models):
        frame[f"temperature_2m_max_{model}"] = (
            17 + season + 0.04 * years + i + rng.normal(0, 3, len(time))
        )
        frame[f"precipitation_sum_{model}"] = np.where(rng.random(len(time)) < 0.3, 5.0, 0.0)
        frame[f"relative_humidity_2m_min_{model}"] = 40 - 0.2 * years + rng.normal(0, 10, len(time))
    return frame


def test_tracc_anchors_the_horizons() -> None:
    assert pj.tracc_warming(2030) == 2.0 and pj.tracc_warming(2050) == 2.7
    assert pj.tracc_warming(2025) == pytest.approx(1.825)  # the 2030-2050 pace, backwards
    assert pj.warming_since_today(2055) == pytest.approx(2.7 + 5 * 1.3 / 50 - 1.825)


def test_indicators_rise_with_warming_and_models_give_a_range() -> None:
    proj = pj.project(_daily(), models=("A", "B"))
    today, *_ = proj.at("jours_chauds", 2025)
    future, low, high = proj.at("jours_chauds", 2055)
    assert future > today and low <= future <= high
    assert proj.hazard_increase(2055) > proj.hazard_increase(2035) > 0


def test_a_model_without_humidity_is_left_out_of_fire_days_not_counted_as_zero() -> None:
    daily = _daily(models=("A", "B")).drop(columns="relative_humidity_2m_min_B")
    proj = pj.project(daily, models=("A", "B"))
    fire = proj.table.loc[("jours_feu", 2055)]
    hot = proj.table.loc[("jours_chauds", 2055)]
    assert fire["low"] == fire["high"]  # a single model: A
    assert hot["low"] < hot["high"]  # both models


def test_longest_dry_spell() -> None:
    assert pj._longest_run(pd.Series([True, True, False, True, True, True, False])) == 3


def test_exposure_grows_with_the_hazard_but_spares_resilient_vegetation() -> None:
    s = np.array([0.0, 0.3, 0.9])
    assert np.allclose(pj.exposure(s, 0.0), s)
    later = pj.exposure(s, 0.5)
    assert later[0] == 0 and (later[1:] > s[1:]).all() and (later <= 1).all()
    stress = np.array([10.0, 22.5, 40.0])  # % of months under stress
    slope = np.array([0.001, 0.0, -0.0015])
    assert np.allclose(pj.sensitivity(stress, slope), [0.0, 0.5, 1.0])


def test_trend_is_extrapolated_where_significant_only() -> None:
    change = pj.trend_extrapolation(np.array([0.001, -0.002]), np.array([1, 0]))
    assert change[0] == pytest.approx(0.12) and np.isnan(change[1])  # 120 months


def test_climate_is_cached_per_model_so_a_limit_keeps_what_arrived(tmp_path, monkeypatch) -> None:
    calls = []

    def fake(lat, lon, model):
        calls.append(model)
        if model == "B" and calls.count("B") == 1:
            raise RuntimeError("Limite gratuite atteinte")
        return _daily(models=(model,)).iloc[:10]

    monkeypatch.setattr(pj, "MODELS", ("A", "B"))
    monkeypatch.setattr(pj, "_get_model", fake)
    with pytest.raises(RuntimeError):
        pj.fetch_climate(45.34, 5.34, tmp_path)
    daily = pj.fetch_climate(45.34, 5.34, tmp_path)  # retried: A comes from the cache
    assert calls == ["A", "B", "B"]
    assert {"temperature_2m_max_A", "temperature_2m_max_B"} <= set(daily.columns)
    pj.fetch_climate(45.31, 5.33, tmp_path)  # same 0.1° cell (45.3, 5.3): nothing asked
    assert calls == ["A", "B", "B"]
