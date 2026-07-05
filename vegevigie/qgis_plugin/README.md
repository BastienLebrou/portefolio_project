# ScruTech — QGIS plugin

Turnkey QGIS Processing tools that wrap the **VegeVigie** pipeline: analyze
vegetation greening/browning trend and drought stress over any extent, straight
from QGIS. One algorithm, **Analyze extent**, runs the whole chain
(Sentinel-2 search → datacube → NDVI → monthly composites → Mann-Kendall + Sen's
slope trend → NDVI-anomaly drought → optional zonal aggregation) and loads the
result layers into your project.

## How it works

ScruTech is a thin QGIS front end. All the science lives in the shared,
UI-agnostic `vegevigie` engine (`src/vegevigie`, driven via
`vegevigie.pipeline.run_pipeline`) — the same engine the CLI uses. The plugin
just turns a QGIS extent + parameters into an engine call and loads the outputs.

## Requirements

- **QGIS ≥ 3.28** (Processing framework).
- **Internet access** to Microsoft Planetary Computer
  (`planetarycomputer.microsoft.com`) for Sentinel-2 imagery.
- The **VegeVigie datacube stack** installed *into QGIS's own Python*:
  `pystac-client planetary-computer odc-stac xarray rioxarray rasterio dask
  geopandas pymannkendall duckdb pydantic pyyaml bottleneck`.

  The plugin checks these on run and, if any are missing, shows the exact
  `pip install …` line for your interpreter. On Windows, run it from the
  **OSGeo4W Shell**:

  ```
  python -m pip install pystac-client planetary-computer odc-stac xarray \
      rioxarray rasterio dask geopandas pymannkendall duckdb pydantic pyyaml bottleneck
  ```

## Install

1. Build the installable zip (bundles the `vegevigie` engine + default config):

   ```
   python qgis_plugin/package.py      # writes qgis_plugin/dist/scrutech.zip
   ```

2. In QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP ▸** pick
   `scrutech.zip`.
3. Restart QGIS. ScruTech appears in the **Processing Toolbox** under *ScruTech*.

(For development you can instead symlink `qgis_plugin/scrutech` into your QGIS
`python/plugins/` folder, but you must then make `vegevigie` importable — either
run `package.py` once to bundle it, or add `src/` to the Python path.)

## Use — analyze an extent in one click

1. **Processing Toolbox ▸ ScruTech ▸ Analyze extent (vegetation trend & drought)**.
2. Set the **extent** (the ▾ lets you use the current map canvas extent, a layer,
   or draw one), the **year window**, **resolution** and **max cloud %**.
3. *(Optional)* pick a **Zones** polygon layer (e.g. communes) for per-zone
   ranking — use *ScruTech ▸ Load commune boundaries* to fetch French communes.
4. Choose an **output folder** and **Run**.

Outputs (GeoTIFF + GeoParquet) are written to the folder and loaded as layers:

- **trend (Sen's slope)** — greening/browning rate per pixel;
- **trend class** — significant greening / browning / none;
- **drought (NDVI anomaly)** — mean standardized anomaly (drought exposure);
- **commune stats** *(if Zones given)* — per-zone slope, % greening/browning,
  anomaly, VCI, also written to a DuckDB table for ranking.

> Tip: to make it a literal one-click button, right-click the algorithm ▸
> *Add to Favorites*, or build a Processing **model**/toolbar button.

## Notes & limits

- Large extents / long windows download more imagery and take longer; start small.
- Cloudy regions leave real gaps — those pixels stay `NoData`, not fabricated.
- Zonal aggregation reprojects your zones to the imagery CRS automatically.
- This plugin is **experimental**; see the repo `README.md` and `CLAUDE.md` §11
  for the roadmap.
