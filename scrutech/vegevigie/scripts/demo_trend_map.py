"""Generate the M4 greening/browning demo map from a SYNTHETIC monthly cube.

Teaching/validation artifact (real cube needs Planetary Computer egress, blocked).
We build a small monthly-NDVI cube (8 years x 40x40 px) with spatially varying
trends — a greening band, a browning patch, stable matrix, plus noise and random
cloud gaps — then run the *real* :func:`vegevigie.trend.trend_dataset` and map the
Sen slope and significant greening/browning classes. Swap in a real ``ndvi_monthly``
cube and the identical call produces the DoD map.

Run: ``uv run python scripts/demo_trend_map.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import ListedColormap

from vegevigie.trend import trend_dataset

DOCS = Path(__file__).resolve().parents[1] / "docs"


def synthetic_monthly_cube(size: int = 40, years: int = 8, seed: int = 7) -> xr.DataArray:
    """Monthly NDVI cube with a spatial gradient of trends and cloud gaps."""
    rng = np.random.default_rng(seed)
    n = years * 12
    times = pd.date_range("2018-01-01", periods=n, freq="MS")
    month = times.month.to_numpy()
    yr = (np.arange(n) / 12.0)[:, None, None]

    # Per-pixel linear trend (NDVI/year): greening in the west, browning blob SE.
    yy, xx = np.mgrid[0:size, 0:size] / size
    trend = 0.02 * (1 - xx) - 0.005  # west greens, east mildly browns
    blob = ((yy - 0.7) ** 2 + (xx - 0.75) ** 2) < 0.12**2
    trend = np.where(blob, -0.03, trend)  # strong browning patch

    seasonal = 0.15 * np.sin(2 * np.pi * (month - 4) / 12)[:, None, None]
    base = 0.55 + seasonal + trend[None, :, :] * yr
    noise = rng.normal(0, 0.03, (n, size, size))
    ndvi = np.clip(base + noise, 0, 1)

    # Random cloud gaps (~20% of pixel-months missing).
    ndvi[rng.random((n, size, size)) < 0.2] = np.nan

    return xr.DataArray(
        ndvi,
        dims=("time", "y", "x"),
        coords={"time": times, "y": np.arange(size), "x": np.arange(size)},
        name="ndvi_monthly",
    )


def main() -> None:
    cube = synthetic_monthly_cube()
    result = trend_dataset(cube, alpha=0.05, min_valid=6)

    slope = result["sen_slope"] * 12.0  # per-month -> per-year for readability
    tclass = result["trend_class"]
    n_green = int((tclass == 1).sum())
    n_brown = int((tclass == -1).sum())

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    vmax = 0.04
    im = axes[0].imshow(slope, cmap="RdYlGn", vmin=-vmax, vmax=vmax)
    axes[0].set_title("Sen's slope (NDVI / year)")
    fig.colorbar(im, ax=axes[0], fraction=0.046, pad=0.04)

    # Discrete class map: browning / no-trend / greening.
    class_cmap = ListedColormap(["#c0392b", "#efefef", "#2e8b57"])
    axes[1].imshow(tclass, cmap=class_cmap, vmin=-1.5, vmax=1.5)
    axes[1].set_title(f"Significant trend class (p<0.05)\ngreening={n_green}  browning={n_brown}")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in ["#2e8b57", "#efefef", "#c0392b"]]
    axes[1].legend(handles, ["greening", "no trend", "browning"], loc="lower left", fontsize=8)

    for ax in axes:
        ax.set_axis_off()
    fig.suptitle(
        "VegeVigie M4 — per-pixel Mann-Kendall + Sen's slope "
        "(SYNTHETIC cube; real scene pending egress)",
        fontsize=11,
    )
    fig.tight_layout()
    out = DOCS / "trend_map_demo.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}  (greening={n_green}, browning={n_brown} px)")


if __name__ == "__main__":
    main()
