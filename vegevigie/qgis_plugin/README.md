# ScruTech — QGIS plugin

Turnkey QGIS Processing tools for the ScruTech pillars, straight from QGIS:

- **VegeVigie** — **Analyze extent** runs the whole vegetation chain over any
  extent (Sentinel-2 search → datacube → NDVI → monthly composites → Mann-Kendall
  + Sen's slope trend → NDVI-anomaly drought → optional zonal aggregation) and
  loads the result layers into your project.
- **PAF (forest fire)** — **Interface habitat-forêt (WUI)** computes the frontier
  line and contact band between a forest layer and a built-up layer (the
  débroussaillement / defence zone). Lightweight: GeoPandas/Shapely only, no
  datacube stack, no internet.
- **Écobuage** — **Aptitude à l'écobuage** scores controlled-burn suitability from
  aligned criterion rasters into a 0-100 map + 3-class zoning (weighted
  multi-criteria). GDAL/numpy only (bundled with QGIS), no internet.

ScruTech is a **hub**: one Processing provider gathering the ScruTech projects as
turnkey tools.

## How it works

ScruTech is a thin QGIS front end. All the science lives in the shared,
UI-agnostic `vegevigie` engine (`src/vegevigie`, driven via
`vegevigie.pipeline.run_pipeline`) — the same engine the CLI uses. The plugin
just turns a QGIS extent + parameters into an engine call and loads the outputs.

## Requirements

- **QGIS ≥ 3.28** (Processing framework).
- **Internet access** to Microsoft Planetary Computer
  (`planetarycomputer.microsoft.com`) for Sentinel-2 imagery.
- The **VegeVigie datacube stack** (`pystac-client planetary-computer odc-stac
  xarray rioxarray rasterio dask geopandas pymannkendall duckdb pydantic pyyaml
  bottleneck`) available to the algorithm — in one of two ways:

### Recommended: an external Python (no QGIS pollution)

Installing rasterio/GDAL into QGIS's bundled Python can clash with QGIS's own
GDAL. Instead, use a separate venv that already has the stack — e.g. the project's
`uv` venv created by `cd vegevigie && uv sync` — and set the algorithm's
**Python executable** parameter to it:

```
<repo>/vegevigie/.venv/Scripts/python.exe    # Windows
<repo>/vegevigie/.venv/bin/python            # macOS/Linux
```

ScruTech then runs the engine in that interpreter (as a subprocess) and only loads
the resulting layers into QGIS. Nothing is installed into QGIS.

### Alternatively: install into QGIS's Python

Leave *Python executable* empty to run in-process. Then the stack must be in QGIS's
Python — on Windows install it from the **OSGeo4W Shell** (Start ▸ QGIS ▸ OSGeo4W
Shell), then restart QGIS:

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

## Use — forest/built-up interface (PAF)

1. **Processing Toolbox ▸ ScruTech ▸ PAF — forest fire ▸ Interface habitat-forêt (WUI)**.
2. Pick a **Forest zones** layer (e.g. VegeVigie-classified vulnerable vegetation)
   and a **Built-up zones** layer.
3. Set the **contact distance** (default 50 m — the French OLD débroussaillement
   footprint) and the **metric CRS** (Lambert-93 by default).
4. **Run**. Two layers are produced and loaded:
   - **Interface line** — the forest edge within the contact distance of a building;
   - **Interface zone** — the forest band to defend/clear.

   Frontier length (km) and band area (ha) are printed in the log. Needs only
   GeoPandas/Shapely (bundled engine) — no internet, no datacube stack.

## Use — écobuage aptitude (multi-criteria)

1. **Processing Toolbox ▸ ScruTech ▸ Écobuage ▸ Aptitude à l'écobuage**.
2. Provide **aligned** criterion rasters (same grid): combustible, embroussaillement,
   accessibility and fire history in `[0, 1]`; slope in percent; plus an optional
   **exclusion** mask (>0 = à exclure).
3. Adjust the **weights** if needed (default 25/25/20/15/15).
4. **Run** → two rasters: **Aptitude (0-100)** and **Classes** (0 exclure /
   1 à étudier / 2 prioritaire). Pixel counts per class are printed in the log.

   Align the criterion rasters first (e.g. *GDAL ▸ Warp* or *Align rasters*). GDAL +
   numpy only — no internet, no datacube stack.

## Notes & limits

- Large extents / long windows download more imagery and take longer; start small.
- Cloudy regions leave real gaps — those pixels stay `NoData`, not fabricated.
- Zonal aggregation reprojects your zones to the imagery CRS automatically.
- This plugin is **experimental**; see the repo `README.md` and `CLAUDE.md` §11
  for the roadmap.
