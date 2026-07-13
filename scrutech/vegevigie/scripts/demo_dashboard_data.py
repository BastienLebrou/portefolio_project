"""Generate SYNTHETIC dashboard inputs so the M7 demo runs with zero network.

The live pipeline needs Planetary Computer egress (blocked here), so this writes
plausible commune stats + a drought timeline straight into data/processed/, in the
exact schema the real pipeline emits (zonal_stats GeoParquet, vegevigie.duckdb
table commune_stats, drought_timeline parquet). Then:

    python scripts/demo_dashboard_data.py
    vegevigie dashboard        # or: streamlit run src/vegevigie/dashboard/app.py

Everything it writes is under data/ (gitignored) and clearly labelled synthetic.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from vegevigie.store import write_duckdb, write_geoparquet

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
L93 = "EPSG:2154"
# A 4x4 grid of 5 km "communes" near Alba-la-Romaine (Ardèche), in Lambert-93.
ORIGIN_X, ORIGIN_Y, CELL, N = 810_000, 6_380_000, 5_000, 4


def synthetic_communes(seed: int = 7) -> gpd.GeoDataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for row in range(N):
        for col in range(N):
            x0 = ORIGIN_X + col * CELL
            y0 = ORIGIN_Y + row * CELL
            # West-to-east greening->browning gradient + noise, so ranks differ.
            grad = 0.018 * (1 - col / (N - 1)) - 0.009
            slope = grad + rng.normal(0, 0.003)
            greening = max(0.0, 100 * (slope + 0.01) / 0.02) if slope > 0 else rng.uniform(0, 15)
            browning = max(0.0, 100 * (-slope + 0.01) / 0.02) if slope < 0 else rng.uniform(0, 15)
            rows.append(
                {
                    "code": f"07{row}{col}",
                    "nom": f"Commune {row}-{col}",
                    "mean_sen_slope": round(slope, 5),
                    "pct_greening": round(min(greening, 100.0), 1),
                    "pct_browning": round(min(browning, 100.0), 1),
                    "mean_anomaly": round(rng.normal(-0.3 - col * 0.15, 0.2), 3),
                    "min_vci": round(rng.uniform(10, 55), 1),
                    "geometry": box(x0, y0, x0 + CELL, y0 + CELL),
                }
            )
    return gpd.GeoDataFrame(rows, crs=L93)


def synthetic_timeline(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.date_range("2018-01-01", "2025-12-01", freq="MS")
    month_num = months.month.to_numpy()  # numpy, not a (immutable) pandas Index
    seasonal = 0.4 * np.sin(2 * np.pi * (month_num - 4) / 12)
    anomaly = rng.normal(0, 0.3, len(months)) + seasonal
    dry = (months.year.to_numpy() == 2022) & np.isin(month_num, [6, 7, 8])  # a dry summer dip
    anomaly[dry] -= 1.6
    return pd.DataFrame({"time": months, "anomaly_mean": np.round(anomaly, 3)})


def main() -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    communes = synthetic_communes()

    zonal_path = PROCESSED / "zonal_stats_demo.parquet"
    write_geoparquet(communes, zonal_path)
    write_duckdb(communes.drop(columns="geometry"), PROCESSED / "vegevigie.duckdb", "commune_stats")
    synthetic_timeline().to_parquet(PROCESSED / "drought_timeline_demo.parquet")

    greenest = communes.loc[communes["mean_sen_slope"].idxmax(), "nom"]
    print(f"Wrote synthetic demo data to {PROCESSED}")
    print(f"  {len(communes)} communes, greenest: {greenest}")
    print("Now run:  vegevigie dashboard")


if __name__ == "__main__":
    main()
