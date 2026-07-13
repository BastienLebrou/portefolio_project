"""Generate the M5 drought demo (anomaly map + timeline) from a SYNTHETIC cube.

Teaching/validation artifact (real cube needs Planetary Computer egress, blocked).
We simulate 8 years of monthly NDVI with a normal seasonal cycle, then knock down
one summer (2021) to mimic a drought, run the *real*
:func:`vegevigie.drought.drought_dataset` / :func:`drought_timeline`, and show the
anomaly map for the dry summer plus the AOI-mean drought curve. Swap in a real
``ndvi_monthly`` cube and the identical calls produce the DoD figure.

Run: ``uv run python scripts/demo_drought.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from vegevigie.drought import drought_dataset, drought_timeline

DOCS = Path(__file__).resolve().parents[1] / "docs"
DRY_YEAR = 2021


def synthetic_monthly_cube(size: int = 40, years: int = 8, seed: int = 7) -> xr.DataArray:
    """Monthly NDVI with a stable seasonal cycle and one dry summer (2021)."""
    rng = np.random.default_rng(seed)
    n = years * 12
    times = pd.date_range("2016-01-01", periods=n, freq="MS")
    month = times.month.to_numpy()

    seasonal = 0.6 + 0.18 * np.sin(2 * np.pi * (month - 4) / 12)
    data = np.repeat(seasonal[:, None, None], size, axis=1).repeat(size, axis=2)
    data = data + rng.normal(0, 0.02, data.shape)

    # Drought: summer (Jun–Sep) of DRY_YEAR depressed, worse toward the south-east.
    yy, xx = np.mgrid[0:size, 0:size] / size
    severity = 0.05 + 0.20 * (xx + yy) / 2  # 0.05..0.25 NDVI drop
    dry = np.asarray((times.year == DRY_YEAR) & np.isin(times.month, [6, 7, 8, 9]))
    data[dry] -= severity[None, :, :]

    return xr.DataArray(
        np.clip(data, 0, 1),
        dims=("time", "y", "x"),
        coords={"time": times, "y": np.arange(size), "x": np.arange(size)},
        name="ndvi_monthly",
    )


def main() -> None:
    cube = synthetic_monthly_cube()
    ds = drought_dataset(cube)
    timeline = drought_timeline(ds["ndvi_anomaly"])

    # Anomaly map for the peak dry month (August of the dry year).
    peak = pd.Timestamp(f"{DRY_YEAR}-08-01")
    anom_map = ds["ndvi_anomaly"].sel(time=peak)

    fig = plt.figure(figsize=(12, 5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1, 1.3])

    ax0 = fig.add_subplot(gs[0])
    im = ax0.imshow(anom_map, cmap="BrBG", vmin=-3, vmax=3)
    ax0.set_title(f"NDVI anomaly (z-score)\n{peak.strftime('%B %Y')} — drought summer")
    ax0.set_axis_off()
    fig.colorbar(im, ax=ax0, fraction=0.046, pad=0.04, label="σ from normal")

    ax1 = fig.add_subplot(gs[1])
    tvals = timeline["time"].values
    yvals = timeline.values
    ax1.axhline(0, color="0.6", lw=0.8)
    ax1.fill_between(tvals, yvals, 0, where=yvals < 0, color="#a0522d", alpha=0.6)
    ax1.fill_between(tvals, yvals, 0, where=yvals >= 0, color="#2e8b57", alpha=0.6)
    ax1.plot(tvals, yvals, color="0.2", lw=1)
    ax1.set_title("AOI-mean NDVI anomaly timeline (drought curve)")
    ax1.set_ylabel("z-score")
    ax1.grid(alpha=0.25)

    fig.suptitle(
        "VegeVigie M5 — drought stress from NDVI anomalies "
        "(SYNTHETIC cube; real scene pending egress)",
        fontsize=11,
    )
    fig.tight_layout()
    out = DOCS / "drought_demo.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    driest = timeline.to_series().idxmin().date()
    print(f"wrote {out}  (driest month = {driest})")


if __name__ == "__main__":
    main()
