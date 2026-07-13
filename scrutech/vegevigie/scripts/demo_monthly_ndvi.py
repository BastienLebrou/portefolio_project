"""Generate the M3 monthly-composite demo from a SYNTHETIC per-pixel NDVI series.

Teaching/validation artifact (real data path needs Planetary Computer egress,
still blocked). We simulate three years of irregular, cloud-gappy Sentinel-2 NDVI
for a single location — a seasonal cycle plus noise, with scenes randomly dropped
to clouds and one long winter fully missing — then show how
:func:`vegevigie.composite.build_monthly_ndvi` turns it into a clean monthly line,
leaving genuine gaps unfilled. Swap the synthetic series for a real ``ndvi`` cube
pixel and the same code produces the DoD figure.

Run: ``uv run python scripts/demo_monthly_ndvi.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.composite import build_monthly_ndvi

DOCS = Path(__file__).resolve().parents[1] / "docs"


def synthetic_series(seed: int = 7) -> xr.DataArray:
    """Irregular daily-ish NDVI for one pixel over 2018–2020, with cloud gaps."""
    rng = np.random.default_rng(seed)
    # ~ every 5 days (Sentinel-2 revisit), 3 years.
    times = pd.date_range("2018-01-01", "2020-12-31", freq="5D")
    doy = times.dayofyear.to_numpy()
    # Seasonal NDVI: low in winter (~0.35), high in summer (~0.8).
    seasonal = 0.57 + 0.22 * np.sin(2 * np.pi * (doy - 100) / 365)
    noise = rng.normal(0, 0.04, len(times))
    ndvi = seasonal + noise

    # Cloud drops: ~45% of scenes masked (NaN).
    clouds = rng.random(len(times)) < 0.45
    ndvi[clouds] = np.nan
    # One long real gap: no clear scene all of winter 2019-2020 (Dec–Feb).
    winter = (times >= "2019-12-01") & (times <= "2020-02-28")
    ndvi[winter] = np.nan

    return xr.DataArray(
        ndvi.reshape(-1, 1, 1),
        dims=("time", "y", "x"),
        coords={"time": times, "y": [0], "x": [0]},
        name="ndvi",
    )


def main() -> None:
    series = synthetic_series()
    monthly = build_monthly_ndvi(series, fill_max_gap=1)

    raw_t = series["time"].values
    raw_v = series.values.ravel()
    mon_t = monthly["time"].values
    mon_v = monthly.values.ravel()

    n_months = monthly.sizes["time"]
    n_gaps = int(np.isnan(mon_v).sum())

    fig, ax = plt.subplots(figsize=(11, 4.4))
    ax.scatter(raw_t, raw_v, s=14, c="0.7", label="Valid scene NDVI (cloud-masked)", zorder=1)
    ax.plot(
        mon_t,
        mon_v,
        "-o",
        color="#2e8b57",
        lw=2,
        ms=5,
        label="Monthly median composite (gap-filled ≤1 mo)",
        zorder=3,
    )
    # Mark residual gaps (unfilled long gaps) on the baseline.
    gap_mask = np.isnan(mon_v)
    if gap_mask.any():
        ax.scatter(
            mon_t[gap_mask],
            np.full(gap_mask.sum(), 0.30),
            marker="x",
            c="#c0392b",
            s=60,
            label="Unfilled gap (no clear data)",
            zorder=4,
        )

    ax.set_ylim(0.25, 0.95)
    ax.set_ylabel("NDVI")
    ax.set_title(
        "VegeVigie M3 — gap-aware monthly NDVI compositing for one pixel\n"
        f"(SYNTHETIC; {n_months} months, {n_gaps} genuine gaps left unfilled — "
        "real scene pending egress)",
        fontsize=11,
    )
    ax.legend(loc="lower left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out = DOCS / "monthly_ndvi_timeseries.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}  ({n_months} months, {n_gaps} unfilled gaps)")


if __name__ == "__main__":
    main()
