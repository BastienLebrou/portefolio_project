# Glossary — remote sensing & datacube terms

Terms are added the first time the pipeline uses them (CLAUDE.md §10). Kept concise on
purpose: the owner knows Python/GIS/stats; this covers only the remote-sensing / raster-
datacube stack that is new to him.

- **STAC** (SpatioTemporal Asset Catalog) — a JSON standard for describing geospatial
  imagery so it's searchable by space/time/collection. We query it with `pystac-client`
  to find Sentinel-2 scenes over the AOI. *(used from M1)*
- **COG** (Cloud-Optimized GeoTIFF) — a GeoTIFF laid out so you can read just the window
  and resolution you need over HTTP, without downloading the whole file. Sentinel-2 assets
  on Planetary Computer are COGs. *(M2)*
- **Signing** — Planetary Computer asset URLs are time-limited; `planetary_computer.sign()`
  stamps them with a short-lived token before a loader can read them. *(M1)*
- **SCL** (Scene Classification Layer) — a per-pixel 20 m classification band shipped with
  Sentinel-2 L2A (vegetation, bare soil, water, cloud, shadow, snow…). We use it as a mask
  to drop cloud/shadow pixels. *(M2)*
- **Datacube** — imagery stacked into a single N-dimensional array indexed by
  (time, y, x, band), handled lazily with `xarray` + `dask` so operations are defined once
  and computed in chunks. *(M2)*
- **Temporal compositing** — collapsing many irregular observations into one value
  per period. We take the **monthly median** of valid NDVI per pixel: robust to
  residual haze and turning the ~5-day Sentinel-2 revisit into a regular monthly
  grid. *Gap-aware*: a month with no clear observation stays NaN rather than being
  invented; only short gaps are optionally interpolated. *(M3)*
- **Mann-Kendall (MK)** — non-parametric test for a monotonic trend in a time series.
  Sums the sign of every pairwise change (the S statistic), standardizes it with a
  tie-corrected variance to a z-score, and derives a two-sided p-value. Direction +
  significance. **Sen's / Theil–Sen slope** — robust trend magnitude: the median of all
  pairwise slopes (yⱼ−yᵢ)/(j−i), so outliers barely move it. Our vectorized kernel is
  validated against `pymannkendall`. *(M4)*
- **Monthly climatology** — the per-pixel, per-calendar-month "normal" NDVI (mean, std,
  min, max) across all years in the record; the baseline every month is compared to. *(M5)*
- **NDVI anomaly (z-score)** — (NDVI − climatology_mean) / climatology_std for that
  pixel-month. Standardized, so comparable across pixels/seasons; ≈ −1.5σ or lower flags
  drought stress. *(M5)*
- **VCI** (Vegetation Condition Index) — 100 · (NDVI − min) / (max − min) over the
  pixel-month history, in 0–100. 0 = worst on record, 100 = best; low VCI (< ~35) is the
  classic drought flag. Complements the z-score. *(M5)*
- **Zonal statistics** — summarizing a raster inside vector polygons. We rasterize each
  commune onto the value grid (a zone-index raster) and reduce the pixels inside it (mean
  slope, % greening/browning, mean anomaly, min VCI), then store the per-commune table in
  DuckDB + GeoParquet for ranking. *(M6)*
