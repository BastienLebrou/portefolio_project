# ScruTech — QGIS plugin

Turnkey QGIS Processing tools that wrap the **VegeVigie** pipeline: analyze
vegetation greening/browning trend and drought stress over any extent, straight
from QGIS. Run the whole chain (Sentinel-2 search → datacube → NDVI → monthly
composites → Mann-Kendall + Sen's slope trend → NDVI-anomaly drought → zonal
aggregation → ranking) with the one-click **Analyze extent** algorithm, or
**stage by stage** — the stages share a run folder, skip work that is already
done, and chain in the QGIS Model Designer.

## How it works

ScruTech is a thin QGIS front end. All the science lives in the shared,
UI-agnostic `vegevigie` engine (`src/vegevigie`) — the same engine the CLI
drives. Every algorithm builds a small JSON *spec* and hands it to the engine,
either **in-process** or in an **external interpreter**
(`python -m vegevigie.qgis_runner`); both modes stream progress and return the
same result payload.

The pipeline entry stage writes a **run manifest** (`scrutech_run.json`) into
the output folder: the AOI, year window, resolution and thresholds, plus what
each stage produced. Downstream stages need only that folder — and skip
themselves when their outputs are already up to date (untick-able via the
advanced *Force recompute* parameter).

## The toolbox

| Algorithm | What it does |
|---|---|
| **Analyze extent** (Analysis) | The whole pipeline in one click; loads styled layers. |
| **1 — Search scenes** (Pipeline stages) | STAC search; starts the run folder + manifest. |
| **2 — Build NDVI composites** | Datacube + SCL cloud mask + monthly medians (the heavy stage). |
| **3 — Compute trend** | Per-pixel Mann-Kendall + Sen's slope → slope / class / p-value rasters. |
| **4 — Compute drought stress** | NDVI anomaly + VCI rasters + AOI drought timeline. |
| **5 — Zonal statistics** | Per-zone stats → GPKG (loaded) + GeoParquet + DuckDB. |
| **6 — Rank zones** | Top-N zones by any zonal metric (DuckDB query) → log + CSV. |
| **Load commune boundaries** (Data) | Any French département's communes, QGIS-native download, no deps. |

Stages 2–6 take the **Run folder** produced by stage 1 (or by *Analyze
extent*), so you can chain them in the **Model Designer** (wire each stage's
*Run folder* output into the next stage's input), batch-run them, re-rank with
different metrics, or force just one stage without re-downloading anything.

Result layers load with bundled styles: diverging brown→green trend ramp,
categorized trend classes, drought anomaly and VCI ramps, graduated commune
polygons.

## Requirements

- **QGIS ≥ 3.28** (Processing framework).
- **Internet access** to Microsoft Planetary Computer
  (`planetarycomputer.microsoft.com`) for Sentinel-2 imagery (search +
  composites stages only; trend/drought/zonal/rank run offline from the run
  folder).
- The **VegeVigie datacube stack** (`pystac-client planetary-computer odc-stac
  xarray rioxarray rasterio dask bottleneck geopandas pymannkendall duckdb
  pydantic pyyaml`) available to the engine — in one of two ways:

### Recommended: an external Python (no QGIS pollution)

Installing rasterio/GDAL into QGIS's bundled Python can clash with QGIS's own
GDAL. Instead, use a separate venv that already has the stack — e.g. the
project's `uv` venv created by `cd vegevigie && uv sync` — and set the
algorithms' **Python executable** parameter to it:

```
<repo>/vegevigie/.venv/Scripts/python.exe    # Windows
<repo>/vegevigie/.venv/bin/python            # macOS/Linux
```

ScruTech runs the engine there as a subprocess and only loads the resulting
layers. The path is **remembered** (QgsSettings) and pre-filled next time; it
is also auto-detected from a `VEGEVIGIE_PYTHON` environment variable or the
repo venv in a development checkout. *Load commune boundaries* needs none of
this — it is pure QGIS.

### Alternatively: install into QGIS's Python

Leave *Python executable* empty to run in-process. Then the stack must be in
QGIS's Python — on Windows install it from the **OSGeo4W Shell** (Start ▸ QGIS
▸ OSGeo4W Shell), then restart QGIS:

```
python -m pip install pystac-client planetary-computer odc-stac xarray \
    rioxarray rasterio dask bottleneck geopandas pymannkendall duckdb pydantic pyyaml
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

## Use — one click

1. **Processing Toolbox ▸ ScruTech ▸ Analyze extent (vegetation trend & drought)**.
2. Set the **extent** (the ▾ lets you use the current map canvas extent, a layer,
   or draw one), the **year window**, **resolution** and **max cloud %**.
3. *(Optional)* pick a **Zones** polygon layer (e.g. from *Load commune
   boundaries*) for per-zone stats.
4. Choose an **output folder** (this becomes the run folder) and **Run**.

Loaded layers: Sen's-slope trend, trend class, drought anomaly, minimum VCI,
and (with Zones) the commune statistics — all pre-styled. The p-value raster,
GeoParquet, DuckDB store and drought timeline are written alongside.

## Use — stage by stage / models

1. Run **1 — Search scenes** on an extent → note the reported scene count and
   the **Run folder** output.
2. Feed that folder to **2 — Build NDVI composites**, then **3/4/5/6** in any
   order their inputs allow. Every stage re-run is a no-op when up to date.
3. In the **Model Designer**, drop the stages and wire *Run folder* outputs to
   inputs to build your own one-click model (e.g. search → composites → trend
   → zonal → rank).

## Notes & limits

- Large extents / long windows download more imagery and take longer; start
  small. The composites stage is the only expensive one — everything after it
  reuses its zarr output.
- Cloudy regions leave real gaps — those pixels stay `NoData`, not fabricated.
- Zonal aggregation reprojects your zones to the imagery CRS automatically; the
  zonal layer is written both as GPKG (loads everywhere) and GeoParquet.
- This plugin is **experimental**; see `ROADMAP.md` for findings, planned
  features (HTML report, prebuilt model file, CDSE backend, i18n…) and the
  interconnection architecture, and repo `CLAUDE.md` §11 for context.
