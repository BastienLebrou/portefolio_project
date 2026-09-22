"""Climate projection of a zone at +10, +15, +20 and +30 years, and where it will hit hardest.

Method (pattern scaling, anchored on the official French trajectory):

1. **Local climate, 2000-2050**: daily CMIP6 simulations of several models at the zone's
   centre, downscaled to 10 km on ERA5-Land (Open-Meteo climate API, CC BY 4.0, free for
   non-commercial use only).
2. **Yearly indicators** per model: very hot days (max > 30 °C), longest dry spell, and days
   favourable to fire (hot, dry air, no rain for a week: an approximation, not the official
   IFM fire-weather index).
3. **Regression** of each indicator on the model's local warming (yearly mean of the daily
   maximum, relative to 2016-2035, centred on today). These runs follow a high-emission
   scenario, so the indicator is read at the warming the **TRACC** gives for each horizon
   (France +2 °C in 2030, +2.7 °C in 2050, +4 °C in 2100) instead of the models' own years.
   Local warming is taken equal to the French mean warming: an approximation.
4. **Where**: the climate is one value for the zone (10 km grid). What differs inside the zone
   is its vegetation today: its sensitivity (stress frequency, decline) measured by VegeVigie,
   raised by the climate hazard increase of each horizon.

The +10 year horizon also gets the plain extrapolation of the NDVI trend, where it is
significant: "if the observed trend goes on".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

BASE_YEAR = 2025
HORIZONS = (2035, 2040, 2045, 2055)  # +10, +15, +20, +30 years
# France warming vs 1850-1900 on the TRACC (Trajectoire de réchauffement de référence).
_TRACC = ((2030, 2.0), (2050, 2.7), (2100, 4.0))
OPEN_METEO = "https://climate-api.open-meteo.com/v1/climate"
MODELS = ("EC_Earth3P_HR", "MPI_ESM1_2_XR", "CMCC_CM2_VHR4", "MRI_AGCM3_2_S")
_DAILY = ("temperature_2m_max", "precipitation_sum", "relative_humidity_2m_min")
# Daily variables each indicator needs: a model missing one of them is left out of it.
_NEEDS = {
    "jours_chauds": ("temperature_2m_max",),
    "periode_seche": ("precipitation_sum",),
    "jours_feu": _DAILY,
}
# Indicator: (French label, unit).
INDICATORS = {
    "jours_chauds": ("jours à plus de 30 °C par an", "jours"),
    "periode_seche": ("plus longue période sans pluie", "jours"),
    "jours_feu": ("jours propices aux feux par an", "jours"),
}
# Sensitivity of the vegetation today: stress in 15 % of months is the statistical normal,
# 30 % is very frequent; a Sen slope of -0.003 NDVI/month is "net dépérissement".
_STRESS_NORMAL, _STRESS_HIGH, _DECLINE_FULL = 15.0, 30.0, 0.003
_TREND_MONTHS = 12 * (HORIZONS[0] - BASE_YEAR)


def tracc_warming(year: float) -> float:
    """France warming (°C vs 1850-1900) on the TRACC, linear between its milestones."""
    years, levels = zip(*_TRACC, strict=True)
    if year < years[0]:  # before 2030: the 2030-2050 pace, backwards
        slope = (levels[1] - levels[0]) / (years[1] - years[0])
        return levels[0] - slope * (years[0] - year)
    return float(np.interp(year, years, levels))


def warming_since_today(year: float) -> float:
    return tracc_warming(year) - tracc_warming(BASE_YEAR)


def fetch_climate(
    lat: float, lon: float, cache_dir: Path | None = None, progress=None
) -> pd.DataFrame:
    """Daily 2000-2050 simulations at a point: one column per variable and model.

    The free Open-Meteo tier weighs a request by variables x days (about 400 calls per model
    here, for 600 a minute and 10 000 a day): one request per model, a pause when the minute
    is used up, and the answer cached on the 0.1° point (the ~10 km grid of the data), so a
    rerun or a neighbouring commune costs nothing.
    """
    lat, lon = round(lat, 1), round(lon, 1)
    daily = None
    for i, model in enumerate(MODELS):
        # One cache file per model: a limit hit halfway keeps the models already received.
        cache = cache_dir / f"climat_{lat:.1f}_{lon:.1f}_{model}.parquet" if cache_dir else None
        if cache is not None and cache.is_file():
            part = pd.read_parquet(cache)
        else:
            if progress:
                progress(10 + 10 * i, f"Climat futur : modèle {i + 1}/{len(MODELS)} ({model})…")
            part = _get_model(lat, lon, model)
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                part.to_parquet(cache)
        daily = part if daily is None else daily.merge(part, on="time")
    return daily


def _get_model(lat: float, lon: float, model: str, attempts: int = 3) -> pd.DataFrame:
    import time

    import requests

    params: dict[str, str | float] = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2000-01-01",
        "end_date": "2050-12-31",
        "models": model,
        "daily": ",".join(_DAILY),
    }
    for attempt in range(attempts):
        resp = requests.get(OPEN_METEO, params=params, timeout=180)
        if resp.status_code != 429:
            break
        reason = resp.json().get("reason", "")
        if "Minutely" not in reason or attempt == attempts - 1:
            raise RuntimeError(
                "Limite gratuite du service climatique Open-Meteo atteinte ("
                + (reason or "trop de requêtes")
                + "). Réessayez plus tard : les zones déjà projetées restent en cache."
            )
        time.sleep(65)  # the minute budget is spent: wait for the next one
    resp.raise_for_status()
    part = pd.DataFrame(resp.json()["daily"])
    part["time"] = pd.to_datetime(part["time"])
    # Single-model requests carry plain names: tag them like the multi-model API does.
    return part.rename(columns={v: f"{v}_{model}" for v in _DAILY})


def yearly_indicators(daily: pd.DataFrame, model: str) -> pd.DataFrame:
    """Per-year indicators of one model, plus its yearly mean daily maximum (``tx``)."""
    tx = daily[f"temperature_2m_max_{model}"]
    rain = daily[f"precipitation_sum_{model}"].fillna(0.0)
    rh = daily.get(f"relative_humidity_2m_min_{model}")  # absent from some models
    week_rain = rain.rolling(7, min_periods=1).sum()
    fire = (tx >= 30.0) & (rh <= 30.0) & (week_rain < 1.0) if rh is not None else False
    frame = pd.DataFrame(
        {
            "year": daily["time"].dt.year,
            "tx": tx,
            "hot": tx > 30.0,
            "fire": fire,  # only used where the model has humidity (see project)
            "dry": rain < 1.0,
        }
    )
    out = frame.groupby("year").agg(
        tx=("tx", "mean"), jours_chauds=("hot", "sum"), jours_feu=("fire", "sum")
    )
    out["periode_seche"] = frame.groupby("year")["dry"].apply(_longest_run)
    return out


def _longest_run(flags: pd.Series) -> int:
    """Longest run of consecutive True values."""
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


@dataclass(frozen=True)
class Projection:
    """Indicators today and at each horizon: median of the models and their range."""

    table: pd.DataFrame  # index (indicator, year), columns median / low / high
    models: list[str]

    @property
    def indicators(self) -> list[str]:
        """The indicators at least one model could compute, in INDICATORS order."""
        present = set(self.table.index.get_level_values("indicator"))
        return [name for name in INDICATORS if name in present]

    def at(self, indicator: str, year: int) -> tuple[float, float, float]:
        row = self.table.loc[(indicator, year)]
        return float(row["median"]), float(row["low"]), float(row["high"])

    def hazard_increase(self, year: int) -> float:
        """Mean relative rise of the indicators since today (0.5 = +50 %), never negative."""
        rises = []
        for name in self.indicators:
            today, _, _ = self.at(name, BASE_YEAR)
            future, _, _ = self.at(name, year)
            rises.append((future - today) / max(today, 1.0))
        return max(0.0, float(np.mean(rises)))


def project(daily: pd.DataFrame, models: tuple[str, ...] = MODELS) -> Projection:
    """Regress each indicator on local warming, model by model, and read it on the TRACC."""
    years = (BASE_YEAR, *HORIZONS)
    rows = []
    used = []
    for model in models:
        if not _complete(daily, model, ("temperature_2m_max",)):
            continue
        yearly = yearly_indicators(daily, model)
        warming = yearly["tx"] - yearly.loc[2016:2035, "tx"].mean()
        used.append(model)
        for name in INDICATORS:
            if not _complete(daily, model, _NEEDS[name]):
                continue  # e.g. no humidity in this model: no fire days rather than zeros
            ok = np.isfinite(warming) & np.isfinite(yearly[name].astype(float))
            slope, intercept = np.polyfit(warming[ok], yearly.loc[ok, name].astype(float), 1)
            for year in years:
                value = intercept + slope * warming_since_today(year)
                rows.append((name, year, model, max(0.0, value)))
    if not used:
        raise ValueError("Aucun modèle climatique exploitable pour ce point.")
    values = pd.DataFrame(rows, columns=["indicator", "year", "model", "value"])
    table = values.groupby(["indicator", "year"])["value"].agg(
        median="median", low="min", high="max"
    )
    return Projection(table, used)


def _complete(daily: pd.DataFrame, model: str, variables: tuple[str, ...]) -> bool:
    """The model has these variables, with at most 5 % of days missing."""
    columns = [f"{v}_{model}" for v in variables]
    return all(c in daily and daily[c].isna().mean() <= 0.05 for c in columns)


def sensitivity(stress_pct: np.ndarray | None, sen_slope: np.ndarray | None) -> np.ndarray:
    """Vegetation sensitivity today (0-1): frequent stress or decline, whichever is worse."""
    parts = []
    if stress_pct is not None:
        span = _STRESS_HIGH - _STRESS_NORMAL
        parts.append(np.clip((stress_pct - _STRESS_NORMAL) / span, 0.0, 1.0))
    if sen_slope is not None:
        parts.append(np.clip(-sen_slope / _DECLINE_FULL, 0.0, 1.0))
    if not parts:
        raise ValueError("Il faut au moins la fréquence de stress ou la tendance VegeVigie.")
    return np.fmax.reduce(parts) if len(parts) > 1 else parts[0]


def exposure(sensitivity_today: np.ndarray, hazard_increase: float) -> np.ndarray:
    """Future exposure (0-1): today's sensitivity raised by the climate hazard increase.

    ``1 - (1 - s) ** (1 + h)``: equal to s when the climate does not change, growing with h,
    never above 1, and a resilient pixel (s = 0) stays at 0.
    """
    return 1.0 - (1.0 - sensitivity_today) ** (1.0 + hazard_increase)


def trend_extrapolation(sen_slope: np.ndarray, trend_class: np.ndarray | None) -> np.ndarray:
    """NDVI change by the first horizon if the observed trend goes on (significant only)."""
    change = sen_slope * _TREND_MONTHS
    if trend_class is not None:
        change = np.where(trend_class != 0, change, np.nan)
    return change


def build_projection(
    lat: float,
    lon: float,
    out_dir: Path,
    *,
    stress_tif: str | Path | None = None,
    trend_tif: str | Path | None = None,
    trend_class_tif: str | Path | None = None,
    cache_dir: Path | None = None,
    progress=None,
) -> tuple[list[Path], dict]:
    """Climate table and exposure maps of a zone; returns (written files, summary)."""
    import json

    report = progress or (lambda _p, _m: None)
    report(10, "Projections climatiques CMIP6 de la zone (Open-Meteo)…")
    proj = project(fetch_climate(lat, lon, cache_dir, report))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    csv = out_dir / "projection_climat.csv"
    proj.table.round(1).to_csv(csv)
    summary = {
        "models": proj.models,
        "indicators": {
            name: {
                str(year): [round(v, 1) for v in proj.at(name, year)]
                for year in (BASE_YEAR, *HORIZONS)
            }
            for name in proj.indicators
        },
        "hazard_increase": {str(y): round(proj.hazard_increase(y), 3) for y in HORIZONS},
    }
    summary_path = out_dir / "projection_climat.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    written += [csv, summary_path]

    if stress_tif or trend_tif:
        report(60, "Cartes d'exposition par horizon…")
        written += _exposure_maps(proj, out_dir, stress_tif, trend_tif, trend_class_tif)
    report(100, f"Projection : {len(written)} fichier(s).")
    return written, summary


def _exposure_maps(proj, out_dir, stress_tif, trend_tif, trend_class_tif) -> list[Path]:
    import rasterio

    grid = stress_tif or trend_tif
    with rasterio.open(grid) as ds:
        profile = {**ds.profile, "count": 1, "dtype": "float32", "nodata": np.nan}
        shape, transform, crs = ds.shape, ds.transform, ds.crs
    stress = _read_on(stress_tif, shape, transform, crs)
    slope = _read_on(trend_tif, shape, transform, crs)
    classes = _read_on(trend_class_tif, shape, transform, crs)
    sens = sensitivity(stress, slope)
    written = []
    for year in (BASE_YEAR, *HORIZONS):  # today: no hazard increase, exposure = sensitivity
        values = exposure(sens, proj.hazard_increase(year) if year != BASE_YEAR else 0.0)
        written.append(_write(out_dir / f"exposition_{year}.tif", values, profile))
    if slope is not None:
        change = trend_extrapolation(slope, classes)
        written.append(_write(out_dir / f"ndvi_tendance_{HORIZONS[0]}.tif", change, profile))
    return written


def _read_on(path, shape, transform, crs) -> np.ndarray | None:
    """Band 1 of ``path`` on the reference grid (NaN where missing), or None."""
    if not path:
        return None
    import rasterio
    from rasterio.warp import Resampling, reproject

    out = np.full(shape, np.nan, dtype="float64")
    with rasterio.open(path) as ds:
        src = ds.read(1, masked=True).astype("float64").filled(np.nan)
        reproject(
            src,
            out,
            src_transform=ds.transform,
            src_crs=ds.crs,
            dst_transform=transform,
            dst_crs=crs,
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    return out


def _write(path: Path, array: np.ndarray, profile: dict) -> Path:
    import rasterio

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype("float32"), 1)
    return path
