"""M6 demo: zonal aggregation of a SYNTHETIC trend raster over the REAL communes.

The commune boundaries are real (the 15 Ardèche communes written by `vegevigie aoi`
into data/raw); only the trend raster is synthetic, because the real one needs
Planetary Computer egress (blocked). We build a UTM trend raster over the AOI, run
the *real* zonal + store code, and print the DuckDB commune ranking — proving the
M6 DoD end-to-end (SELECT returns top greening/browning communes). A saved bar
chart makes it eyeball-checkable.

Run (after `uv run vegevigie aoi --small`):
    uv run python scripts/demo_zonal_ranking.py
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rioxarray  # noqa: F401 — registers .rio
import xarray as xr

from vegevigie.store import rank_communes, write_duckdb
from vegevigie.zonal import commune_stats

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
COMMUNES = ROOT / "data" / "raw" / "communes_07.parquet"
AOI = ROOT / "data" / "raw" / "aoi.parquet"
UTM31 = "EPSG:32631"


def synthetic_trend_over_aoi(res: int = 100, seed: int = 7) -> xr.Dataset:
    """A UTM trend raster (sen_slope + trend_class) covering the AOI extent."""
    aoi = gpd.read_parquet(AOI).to_crs(UTM31)
    minx, miny, maxx, maxy = aoi.total_bounds
    x = np.arange(minx, maxx, res)
    y = np.arange(maxy, miny, -res)
    rng = np.random.default_rng(seed)

    # West-to-east greening->browning gradient + noise, so communes rank differently.
    xn = (x - minx) / (maxx - minx)
    slope = (0.02 * (1 - xn))[None, :] - 0.008 + rng.normal(0, 0.004, (len(y), len(x)))
    sen = xr.DataArray(slope, dims=("y", "x"), coords={"y": y, "x": x}).rio.write_crs(UTM31)

    tclass = xr.where(sen > 0.004, 1, xr.where(sen < -0.004, -1, 0))
    return xr.Dataset({"sen_slope": sen, "trend_class": tclass})


def main() -> None:
    communes = gpd.read_parquet(COMMUNES)
    # Restrict to the 15 AOI communes (those overlapping the small bbox).
    aoi_names = set(gpd.read_parquet(AOI)["nom"])
    communes = communes[communes["nom"].isin(aoi_names)].reset_index(drop=True)

    trend = synthetic_trend_over_aoi()
    stats = commune_stats(communes, trend["sen_slope"], trend["trend_class"])

    db = DOCS / "_demo.duckdb"
    write_duckdb(stats.drop(columns="geometry"), db, table="commune_stats")
    top_green = rank_communes(db, "mean_sen_slope", ascending=False, limit=5)
    top_brown = rank_communes(db, "mean_sen_slope", ascending=True, limit=5)
    db.unlink(missing_ok=True)

    print("Top greening communes (synthetic):")
    for _, r in top_green.iterrows():
        print(f"  {r['nom']:<28} {r['mean_sen_slope']:+.5f}")
    print("Top browning communes (synthetic):")
    for _, r in top_brown.iterrows():
        print(f"  {r['nom']:<28} {r['mean_sen_slope']:+.5f}")

    ranked = stats.sort_values("mean_sen_slope")
    colors = ["#2e8b57" if v >= 0 else "#c0392b" for v in ranked["mean_sen_slope"]]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(ranked["nom"], ranked["mean_sen_slope"], color=colors)
    ax.axvline(0, color="0.4", lw=0.8)
    ax.set_xlabel("Mean Sen's slope (NDVI / month)")
    ax.set_title(
        "VegeVigie M6 — commune trend ranking (real communes, SYNTHETIC raster)\n"
        "zonal stats -> DuckDB SELECT ... ORDER BY"
    )
    fig.tight_layout()
    out = DOCS / "commune_ranking_demo.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
