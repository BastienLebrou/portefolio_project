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
- **Mann-Kendall (MK)** — non-parametric test for a monotonic trend in a time series;
  gives direction + p-value. **Sen's / Theil–Sen slope** — robust trend magnitude (median
  of pairwise slopes). *(M4)*
- **VCI** (Vegetation Condition Index) — NDVI rescaled against its per-pixel historical
  min/max to express how the current value compares to the normal range; low VCI flags
  drought stress. *(M5)*
