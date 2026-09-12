"""AOI-only biotrame: hexagonal ecological-priority mesh from a study area alone.

Ties the biotrame vector engine to the ScruTech data sources so the user supplies only an
emprise:

- **maillage** ← :func:`biotrame.hex_grid` (H3) over the AOI;
- **enjeu / connectivité** ← :func:`core.sources.fetch_biodiversity_reservoirs` (Natura 2000,
  ZNIEFF …) aggregated per hexagon;
- **dégradation** (optional) ← zonal mean of a VegeVigie trend raster (browning = degrading).

Score = geometric mean of the axes → 3 classes. Outputs a GeoParquet (L93) + GeoJSON (WGS84)
hexagon layer. The zonal raster maths (rasterio + scipy) live here, not in the biotrame
package, which stays pure-vector.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("vegevigie")

L93 = "EPSG:2154"
WGS84 = "EPSG:4326"


def build_priority_mesh_from_aoi(
    aoi: object,
    out_dir: Path,
    *,
    resolution: int = 8,
    veg_trend_tif: str | Path | None = None,
    mnt_path: str | Path | None = None,
    reservoir_kinds: tuple[str, ...] | None = None,
    corridor_max_m: float = 2000.0,
    browning_scale: float = 0.01,
    tvb_wfs_url: str | None = None,
    tvb_typename: str | None = None,
    progress=None,
) -> tuple[Path, Path, dict]:
    """Build the scored priority mesh for the AOI. Returns (parquet, geojson, info)."""
    from biotrame.mesh import hex_grid
    from biotrame.score import score_mesh
    from core.sources import fetch_biodiversity_reservoirs, fetch_tvb_corridors

    report = progress or (lambda _p, _m: None)
    report(15, "Building the H3 hexagon mesh…")
    grid = hex_grid(aoi, resolution=resolution)

    report(40, "Fetching biodiversity reservoirs (Natura 2000 / ZNIEFF)…")
    reservoirs = fetch_biodiversity_reservoirs(aoi, kinds=reservoir_kinds)

    corridors = None
    if tvb_wfs_url and tvb_typename:
        report(55, "Fetching real TVB corridors (regional SRCE WFS)…")
        try:
            corridors = fetch_tvb_corridors(aoi, tvb_typename, wfs_url=tvb_wfs_url)
        except Exception as exc:  # noqa: BLE001 — fall back to the proximity proxy, don't fail
            logger.warning("TVB fetch failed (%s); using reservoir-proximity proxy.", exc)

    degradation = None
    if veg_trend_tif:
        report(65, "Zonal degradation from the VegeVigie trend raster…")
        degradation = _zonal_browning(grid, veg_trend_tif, browning_scale)

    enjeu_boost = None
    if mnt_path:
        report(72, "Zones humides potentielles (humidité topographique du MNT)…")
        enjeu_boost = _zonal_wetness(grid, mnt_path)

    report(80, "Crossing axes → priority score…")
    scored = score_mesh(
        grid,
        reservoirs,
        degradation=degradation,
        corridor_max_m=corridor_max_m,
        corridors=corridors,
        enjeu_boost=enjeu_boost,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    parquet = out_dir / "biotrame_priority.parquet"
    geojson = out_dir / "biotrame_priority.geojson"
    scored.to_crs(L93).to_parquet(parquet)
    scored.to_crs(WGS84).to_file(geojson, driver="GeoJSON")

    has_tvb = corridors is not None and not corridors.empty
    info = {
        "n_hexagons": int(len(scored)),
        "n_prioritaire": int((scored["classe"] == 2).sum()),
        "n_a_etudier": int((scored["classe"] == 1).sum()),
        "n_reservoirs": int(len(reservoirs)),
        "connectivity_source": "tvb_corridors" if has_tvb else "reservoir_proximity_proxy",
        "axes": ["enjeu", "connectivite"] + (["degradation"] if degradation is not None else []),
        "enjeu_boost": "zones_humides_mnt" if enjeu_boost is not None else None,
        "resolution": resolution,
    }
    report(100, f"Biotrame: {info['n_prioritaire']}/{info['n_hexagons']} hexagones prioritaires.")
    logger.info("Biotrame AOI: %s", info)
    return parquet, geojson, info


def _zonal_browning(grid, trend_tif: str | Path, browning_scale: float) -> pd.Series:
    """Per-hexagon degradation (0-1) from a VegeVigie trend raster: browning = negative slope.

    Zonal mean of the Sen slope per hexagon (nodata/NaN pixels skipped), then a negative mean
    (browning) is rescaled to 0-1 over ``browning_scale`` NDVI-units/step. Greening → 0.
    """
    import rasterio
    from rasterio.features import rasterize
    from scipy import ndimage

    with rasterio.open(trend_tif) as ds:
        arr = ds.read(1).astype("float64")
        transform = ds.transform
        crs = ds.crs or L93
        if ds.nodata is not None:
            arr[arr == ds.nodata] = np.nan

    g = grid.to_crs(crs)
    shapes = [(geom, i + 1) for i, geom in enumerate(g.geometry) if geom is not None]
    labels = rasterize(shapes, out_shape=arr.shape, transform=transform, fill=0, dtype="int32")
    labels = np.where(np.isfinite(arr), labels, 0)  # drop NaN pixels from their hexagon

    idx = np.arange(1, len(g) + 1)
    means = np.asarray(ndimage.mean(np.nan_to_num(arr), labels=labels, index=idx), dtype="float64")
    degradation = np.clip(-means / browning_scale, 0.0, 1.0)
    degradation = np.nan_to_num(degradation, nan=0.0)
    return pd.Series(degradation, index=grid["hex_id"])


def _zonal_wetness(grid, mnt_path: str | Path) -> pd.Series:
    """Per-hexagon wetland potential (0-1) from the DEM (topographic wetness), zonal-averaged.

    Reads the DEM window over the AOI (CRS assumed Lambert-93 if untagged), computes the
    topographic wetness (flat + depression), then the mean per hexagon.
    """
    import rasterio
    from core.cog import raster_source
    from rasterio.features import rasterize
    from rasterio.windows import from_bounds
    from scipy import ndimage

    from vegevigie.wetland import topographic_wetness

    g = grid.to_crs(L93)
    minx, miny, maxx, maxy = g.total_bounds
    with rasterio.open(raster_source(mnt_path)) as ds:
        pad = 300.0  # metres, so the neighborhood filter has context at the edges
        win = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad, ds.transform)
        dem = ds.read(1, window=win, boundless=True, fill_value=np.nan).astype("float64")
        win_transform = ds.window_transform(win)
        if ds.nodata is not None:
            dem[dem == ds.nodata] = np.nan
        cell = abs(ds.transform.a)

    wetness = topographic_wetness(dem, cell)
    shapes = [(geom, i + 1) for i, geom in enumerate(g.geometry) if geom is not None]
    labels = rasterize(
        shapes, out_shape=wetness.shape, transform=win_transform, fill=0, dtype="int32"
    )
    idx = np.arange(1, len(g) + 1)
    means = np.asarray(ndimage.mean(wetness, labels=labels, index=idx), dtype="float64")
    return pd.Series(np.nan_to_num(means, nan=0.0), index=grid["hex_id"])
