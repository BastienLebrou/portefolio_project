"""Engine-spine tests — run manifest + stage functions, offline (§8).

The composites stage needs the network-bound datacube loader, so it isn't run
here; instead a synthetic monthly-NDVI zarr (the composites stage's contract)
feeds the trend / drought / zonal / rank stages end-to-end.
"""

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rioxarray  # noqa: F401 — registers the .rio accessor
import xarray as xr
from shapely.geometry import box

from vegevigie.pipeline import build_settings
from vegevigie.stages import (
    STAGE_DROUGHT,
    STAGE_RANK,
    STAGE_SEARCH,
    STAGE_TREND,
    STAGE_ZONAL,
    RunManifest,
    StageInputError,
    load_manifest_settings,
    monthly_path,
    run_stage,
    settings_fingerprint,
)

CRS = "EPSG:32631"

FAKE_ITEMS = [
    {"id": "S2_A", "properties": {"datetime": "2020-06-01", "eo:cloud_cover": 10}},
    {"id": "S2_B", "properties": {"datetime": "2020-07-01", "eo:cloud_cover": 20}},
]


class FakeBackend:
    """Offline StacBackend double that counts real searches."""

    stac_url = "fake://stac"

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.searches = 0

    def search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.searches += 1
        return self.items

    def sign(self, item: Any) -> Any:
        return item


def _settings(tmp_path: Path, **overrides: Any):
    return build_settings((4.5, 44.5, 4.7, 44.6), 2020, 2021, data_dir=tmp_path, **overrides)


def _write_synthetic_monthly(path: Path) -> None:
    """24 monthly steps on a 4x4 grid: left half greens, right half browns."""
    time = pd.date_range("2020-01-01", periods=24, freq="MS")
    x = np.arange(0.5, 4, 1.0)
    y = np.arange(3.5, 0, -1.0)  # north-up
    t = np.arange(24, dtype="float64")
    data = np.empty((24, 4, 4))
    data[:, :, :2] = (0.3 + 0.01 * t)[:, None, None]
    data[:, :, 2:] = (0.7 - 0.01 * t)[:, None, None]
    da = xr.DataArray(
        data, dims=("time", "y", "x"), coords={"time": time, "y": y, "x": x}, name="ndvi_monthly"
    ).rio.write_crs(CRS)
    path.parent.mkdir(parents=True, exist_ok=True)
    da.to_dataset().to_zarr(path, mode="w")


def _two_zones() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"code": ["A", "B"], "nom": ["Left", "Right"]},
        geometry=[box(0, 0, 2, 4), box(2, 0, 4, 4)],
        crs=CRS,
    )


# --- manifest ----------------------------------------------------------------


def test_fingerprint_ignores_paths(tmp_path: Path) -> None:
    a = _settings(tmp_path / "a")
    b = _settings(tmp_path / "b")
    assert settings_fingerprint(a) == settings_fingerprint(b)
    assert settings_fingerprint(a) != settings_fingerprint(_settings(tmp_path / "a", resolution=20))


def test_manifest_survives_reload_and_resets_on_param_change(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manifest = RunManifest.for_settings(settings)
    artifact = tmp_path / "raw" / "items.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}")
    manifest.record(STAGE_SEARCH, {"items": artifact}, {"scene_count": 2})

    reloaded = RunManifest.for_settings(settings)
    assert reloaded.fresh(STAGE_SEARCH) == {"items": artifact}
    assert reloaded.meta(STAGE_SEARCH)["scene_count"] == 2

    changed = RunManifest.for_settings(_settings(tmp_path, resolution=20))
    assert changed.fresh(STAGE_SEARCH) is None  # new fingerprint -> fresh ledger


def test_manifest_stores_relative_paths_and_checks_disk(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manifest = RunManifest.for_settings(settings)
    artifact = tmp_path / "processed" / "trend.tif"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("x")
    manifest.record(STAGE_TREND, {"sen_slope": artifact})

    import json

    stored = json.loads((tmp_path / "scrutech_run.json").read_text())
    assert stored["stages"][STAGE_TREND]["artifacts"]["sen_slope"] == "processed/trend.tif"

    artifact.unlink()
    assert RunManifest.for_settings(settings).fresh(STAGE_TREND) is None  # gone from disk


def test_load_manifest_settings_round_trip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    RunManifest.for_settings(settings).save()
    restored = load_manifest_settings(tmp_path)
    assert settings_fingerprint(restored) == settings_fingerprint(settings)
    assert restored.paths.data_dir == tmp_path


def test_load_manifest_settings_missing(tmp_path: Path) -> None:
    with pytest.raises(StageInputError, match="search"):
        load_manifest_settings(tmp_path)


# --- search stage (fake backend) ----------------------------------------------


def test_search_stage_caches_and_forces(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    backend = FakeBackend(FAKE_ITEMS)

    first = run_stage(STAGE_SEARCH, settings, backend=backend)
    assert first.meta["scene_count"] == 2
    assert first.artifacts["items"].exists()
    assert backend.searches == 1

    second = run_stage(STAGE_SEARCH, settings, backend=backend)
    assert second.skipped
    assert second.meta["scene_count"] == 2
    assert backend.searches == 1  # no re-query

    forced = run_stage(STAGE_SEARCH, settings, backend=backend, force=True)
    assert not forced.skipped
    assert backend.searches == 2


# --- trend / drought / zonal / rank on synthetic composites --------------------


def test_stage_chain_on_synthetic_monthly(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _write_synthetic_monthly(monthly_path(settings))

    trend = run_stage(STAGE_TREND, settings)
    assert set(trend.artifacts) == {"sen_slope", "trend_class", "mk_pvalue"}
    assert all(p.exists() for p in trend.artifacts.values())
    assert trend.meta["greening_pixels"] == 8
    assert trend.meta["browning_pixels"] == 8

    again = run_stage(STAGE_TREND, settings)
    assert again.skipped  # manifest cache hit

    drought = run_stage(STAGE_DROUGHT, settings)
    assert set(drought.artifacts) == {"anomaly", "min_vci", "timeline"}
    assert all(p.exists() for p in drought.artifacts.values())

    zonal = run_stage(STAGE_ZONAL, settings, zones=_two_zones())
    assert set(zonal.artifacts) == {"stats_parquet", "stats_gpkg", "duckdb"}
    stats = gpd.read_parquet(zonal.artifacts["stats_parquet"])
    left = stats.loc[stats["nom"] == "Left"].iloc[0]
    right = stats.loc[stats["nom"] == "Right"].iloc[0]
    assert left["mean_sen_slope"] == pytest.approx(0.01, abs=1e-3)
    assert right["mean_sen_slope"] == pytest.approx(-0.01, abs=1e-3)
    assert left["pct_greening"] == pytest.approx(100.0)
    assert "min_vci" in stats.columns

    cached = run_stage(STAGE_ZONAL, settings, zones=_two_zones())
    assert cached.skipped  # same zones content -> cache hit

    moved = _two_zones()
    moved.loc[0, "geometry"] = box(0, 0, 2, 3.5)
    recomputed = run_stage(STAGE_ZONAL, settings, zones=moved)
    assert not recomputed.skipped  # changed zones invalidate the cache

    rank = run_stage(STAGE_RANK, settings, metric="mean_sen_slope", limit=2)
    assert rank.artifacts["csv"].exists()
    assert rank.meta["rows"][0][0] == "Left"  # top greening zone


def test_trend_stage_requires_composites(tmp_path: Path) -> None:
    with pytest.raises(StageInputError, match="composites"):
        run_stage(STAGE_TREND, _settings(tmp_path))


def test_zonal_stage_requires_zones_and_trend(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="zones"):
        run_stage(STAGE_ZONAL, settings)
    with pytest.raises(StageInputError, match="trend"):
        run_stage(STAGE_ZONAL, settings, zones=_two_zones())


def test_unknown_stage_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown stage"):
        run_stage("nope", _settings(tmp_path))
