# CLAUDE.md — VegeVigie

> **VegeVigie — Vigie de la végétation.** A reproducible geodata-engineering pipeline that
> watches vegetation health over time from Sentinel-2 imagery: it builds NDVI time series,
> detects statistically significant greening/browning trends, and flags drought stress —
> aggregated to the commune level and served through a small dashboard.
>
> This is a portfolio project. Two goals, equal weight: (1) ship a clean, public, recruiter-ready
> geodata-engineering repo; (2) teach the author the modern remote-sensing / datacube
> stack as we build. Treat "explain what you're doing and why" as a first-class requirement,
> not an afterthought.

## 0. Who this is for (project owner context)

The owner is a strong Python GIS developer (GeoPandas, Shapely, PostGIS, DuckDB,
GeoParquet, QGIS, API integration) and knows trend statistics from R (Mann-Kendall,
Sen's slope, Pettitt/Buishand). He is new to the remote-sensing datacube stack (STAC,
COG, xarray/dask, cloud masking). So:

- **Don't** over-explain Python, pandas, SQL, or geospatial vector basics — he has those.
- **Do** explain, clearly and concisely, every remote-sensing / raster-datacube concept the
  first time it appears: STAC, COG, signing, SCL cloud masking, UTM tiling, datacube
  chunking, lazy dask evaluation, temporal compositing, per-pixel trend testing at scale. A
  3–6 line explanation in the relevant module docstring or a `notebooks/` cell is expected.
- Implement the trend stats in Python (they exist in R in his head; port them, don't
  assume the library does it silently).

## 1. What we're building (scope)

In scope (v1):

1. Define an Area of Interest (default: Ardèche, dept 07, France) from official admin
   boundaries.
2. Search Sentinel-2 L2A over the AOI for a multi-year window (default 2018–2025), filter
   by cloud cover.
3. Build a lazy xarray datacube (Red, NIR, SCL), cloud/shadow-mask it, compute NDVI.
4. Build clean monthly median NDVI composites (gap-aware).
5. Run per-pixel Mann-Kendall + Sen's slope → a greening/browning trend raster with
   significance.
6. Compute drought stress as NDVI anomalies vs a per-pixel monthly climatology (z-score
   / VCI).
7. Zonal aggregation to communes → store in DuckDB + GeoParquet; rank communes
   by trend and drought exposure.
8. A small Streamlit + leafmap dashboard: trend map, per-commune time series, drought
   timeline.

**Out of scope (v1)** — do not build unless asked: machine-learning land-cover
classification, SAR, multi-sensor fusion, cloud deployment, auth/user accounts, anything
that needs paid data or a paid compute tier.

**Guiding principle: start small, scale later.** First make the whole pipeline work end-to-end
on a tiny AOI (one commune or a small bbox) and one year. Only then scale to the full
department and full time range, using coarser resolution and monthly compositing to stay
laptop-tractable.

## 2. Tech stack (pinned choices — don't substitute without asking)

- Python 3.11+, dependency + venv management with **uv** (`pyproject.toml`, `uv.lock`).
- Data access: `pystac-client` + `planetary-computer` → Microsoft Planetary
  Computer public STAC (`sentinel-2-l2a` collection). It's free and anonymous-read, but
  asset hrefs must be signed with `planetary_computer.sign()`. Keep a thin adapter so
  a Copernicus Data Space Ecosystem (CDSE) backend can be added later without
  touching callers.
- Datacube: `odc-stac` (`odc.stac.load`) as primary loader (handles SCL resampling +
  grouping by solar day cleanly); `stackstac` acceptable as a documented alternative.
- Raster/array: `xarray`, `rioxarray`, `dask`, `rasterio`, `numpy`.
- Trend stats: `pymannkendall` for reference/validation, plus a vectorized Mann-Kendall +
  Theil–Sen implementation for the datacube (see §5). `scipy` allowed.
- Vector / tabular / store: `geopandas`, `shapely`, `duckdb` (with the spatial extension),
  `pyarrow` (GeoParquet), `zarr` for cached datacubes.
- CLI: `typer`. Dashboard: `streamlit` + `leafmap` (+ `plotly` for charts).
- Quality: `pytest`, `ruff` (lint + format), `pre-commit`, `mypy` (lenient), GitHub Actions CI.

If a pinned library proves unavailable or broken in the environment, stop and report with the
error and a proposed alternative — don't silently swap in something else.

## 3. Repository layout

```
vegevigie/
├── CLAUDE.md                     # this file
├── README.md                     # portfolio front door (see §9)
├── pyproject.toml                # uv-managed
├── uv.lock
├── .gitignore                    # data/ caches, .zarr, .duckdb, notebooks checkpoints
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── config/
│     └── default.yaml            # AOI, date range, resolution, params (pydantic-loaded)
├── data/                         # ALL gitignored
│     ├── raw/                    # admin boundaries, STAC item cache (JSON)
│     ├── interim/                # datacubes (.zarr), NDVI composites
│     └── processed/              # geoparquet outputs, vegevigie.duckdb
├── src/vegevigie/
│     ├── __init__.py
│     ├── config.py               # pydantic Settings, loads config/default.yaml
│     ├── cli.py                  # typer app; one command per pipeline stage
│     ├── aoi.py                  # load/clip admin boundaries -> AOI GeoParquet
│     ├── catalog.py              # STAC search + sign + cache item list
│     ├── datacube.py             # odc.stac.load -> xarray cube (Red, NIR, SCL)
│     ├── indices.py              # SCL mask + NDVI
│     ├── composite.py            # monthly median compositing, gap handling
│     ├── trend.py                # vectorized Mann-Kendall + Sen's slope
│     ├── drought.py              # monthly climatology, anomaly / VCI
│     ├── zonal.py                # zonal stats to communes
│     ├── store.py                # DuckDB + GeoParquet IO helpers
│     └── dashboard/
│          └── app.py             # streamlit entrypoint
├── notebooks/                    # short teaching + exploration notebooks (one per concept)
├── tests/
└── docs/
     └── glossary.md              # RS terms explained (STAC, COG, SCL, VCI, MK, Sen…)
```

## 4. CLI contract (build these)

Every stage is idempotent, reads from config, writes to `data/`, and can run standalone.
Prefer caching: skip work if the output exists and inputs are unchanged (add `--force`).

```
vegevigie aoi                # build AOI GeoParquet from admin boundaries (dept 07 default)
vegevigie search             # STAC search -> cache signed item list (JSON) in data/raw
vegevigie cube               # build datacube (.zarr) for AOI + window
vegevigie ndvi               # SCL-mask + NDVI + monthly composites -> data/interim
vegevigie trend              # per-pixel Mann-Kendall + Sen's slope -> trend raster
vegevigie drought            # NDVI anomalies / VCI -> drought raster + timeline
vegevigie zonal              # aggregate rasters to communes -> DuckDB + GeoParquet
vegevigie dashboard          # launch Streamlit app
vegevigie run                # full pipeline end-to-end (small-AOI smoke by default)
```

Global flags: `--config PATH`, `--aoi NAME`, `--start YYYY`, `--end YYYY`, `--res METERS`,
`--force`, `--verbose`.

## 5. The hard part, explained (per-pixel trend at scale)

This is the technically interesting bit and the owner's differentiator (he knows the stats from
R). Handle it carefully and teach it:

- **Mann-Kendall** = non-parametric test for a monotonic trend in a time series; returns
  trend direction + a p-value (significance). **Sen's / Theil–Sen slope** = robust magnitude
  of that trend (median of pairwise slopes). Together: "is this pixel greening or browning,
  significantly, and how fast?"
- Naïvely looping `pymannkendall` over every pixel of a department-scale cube is far too
  slow. Required approach:
  - Reduce the temporal axis to one clean value per month (monthly median
    composites) before trend testing — fewer, denoised time steps.
  - Implement a vectorized MK + Theil–Sen that operates over the (time) axis of an
    `xarray.DataArray`, applied blockwise with dask (`xr.apply_ufunc(...,
    dask="parallelized", vectorize=...)` or a hand-written numpy kernel over chunks).
  - Validate the vectorized version against `pymannkendall` on a handful of sample
    pixels in a test — they must match.
  - Keep it tractable: default to a coarser resolution (e.g. 20–60 m) for the
    department-wide trend pass; keep 10 m only for small AOIs. Make resolution a config
    knob.
- Output a trend raster with at least: `sen_slope`, `mk_pvalue`, `trend_class` (greening /
  browning / no-significant-trend at p<0.05).

Key Sentinel-2 constants to hard-code (and comment):

- NDVI = (B08 NIR − B04 Red) / (B08 + B04), both native 10 m.
- SCL (Scene Classification Layer, 20 m) mask — keep {4 vegetation, 5 bare, 6 water, 7
  unclassified}; drop {0 nodata, 1 saturated, 2 dark, 3 cloud-shadow, 8 cloud-med, 9
  cloud-high, 10 cirrus, 11 snow}.
- Planetary Computer hrefs expire → always `planetary_computer.sign(item)` before
  loading.
- Sentinel-2 tiles are per-UTM-zone; note/handle CRS when an AOI spans zones (Ardèche
  is fine in a single zone).

## 6. Milestones (vertical slices — deliver in order, each independently runnable)

- **M0 — Scaffold.** Repo, uv env, `pyproject.toml`, ruff/pre-commit/CI green, `config.py`
  + `default.yaml`, empty CLI wired with typer, `.gitignore`. DoD: `vegevigie --help`
  runs; CI passes.
- **M1 — AOI + STAC search (tiny).** `aoi` + `search` on a small bbox, 1 year. DoD: prints N
  scenes found, caches a signed item list, writes AOI GeoParquet.
- **M2 — Datacube + NDVI (one small tile).** `cube` + SCL mask + NDVI. DoD: a plotted
  NDVI scene for one clear date saved to `docs/` — visibly masked clouds.
- **M3 — Monthly composites.** Gap-aware median compositing → clean per-month NDVI
  stack. DoD: a per-pixel monthly time series plotted for one location.
- **M4 — Trend (the headline).** Vectorized MK + Sen's slope, validated vs `pymannkendall`.
  DoD: greening/browning map for the small AOI + a passing validation test.
- **M5 — Drought stress.** Monthly climatology + anomaly/VCI + a drought timeline. DoD:
  anomaly map for a known dry year looks right.
- **M6 — Scale + zonal.** Run department-wide at coarse res; zonal-aggregate to
  communes into DuckDB + GeoParquet; commune ranking query. DoD: SELECT returns
  top greening/browning communes.
- **M7 — Dashboard.** Streamlit + leafmap: trend map layer, click-a-commune time series,
  drought timeline. DoD: `vegevigie dashboard` opens and is navigable.
- **M8 — Portfolio polish.** README with hero images + architecture diagram,
  `docs/glossary.md`, a reproducible `vegevigie run` demo on the tiny AOI, screenshots,
  short methodology write-up. DoD: a stranger can clone, run the smoke demo, and
  understand it in 5 minutes.

**Do not jump ahead. A working thin slice beats a half-built wide one.**

## 7. Coding standards & conventions

- Code, docstrings, comments, commit messages, README: **English** (international
  portfolio value). Domain terms may stay French where natural (commune, département);
  define them in the glossary.
- Type hints everywhere; `ruff format` + `ruff check` clean before any commit.
- Pure functions for the science (masking, NDVI, MK, Sen, anomaly) — no I/O inside them
  — so they're unit-testable. I/O lives in `store.py` / `catalog.py`.
- Config-driven, no magic numbers in logic — thresholds (cloud %, p-value, resolution,
  date window) come from config.
- Deterministic + reproducible: same config → same outputs. Cache aggressively; never
  re-download if cached.
- Log with `logging` (not `print`), `--verbose` raises level.
- Small, atomic commits per meaningful step, conventional-commit style (`feat:`, `fix:`,
  `docs:`, `test:`).

## 8. Testing

- `pytest` for every pure function. Priorities: SCL mask correctness (synthetic SCL array in
  → known mask out), NDVI math, MK/Sen vectorized == `pymannkendall` on sample
  series, composite gap handling.
- Use tiny synthetic arrays and one small cached fixture scene — tests must run offline,
  fast, no network.
- CI runs lint + tests on push.

## 9. README (portfolio front door — build in M8)

Must contain, in order: a one-line hook + hero trend map image; the problem ("where and
how fast is vegetation greening/browning, and where is drought stress emerging?"); an
architecture diagram (STAC → datacube → NDVI → composites → trend/drought → DuckDB
→ dashboard); the tech stack; a Quickstart (`uv sync` → `vegevigie run` small-AOI demo);
sample outputs (trend map, a commune time series, drought timeline); a short
**Methodology** section (Sentinel-2, SCL masking, monthly compositing, Mann-Kendall +
Sen's slope, VCI); and honest **Limitations & next steps** (resolution/compute trade-offs,
cloud gaps, SAR/ML as future work).

Tagline: *"VegeVigie — sentinelle de la végétation. NDVI trends & drought stress from
Sentinel-2, commune by commune."*

## 10. How to work in this repo (agent guidance)

- Work milestone by milestone (§6), thin vertical slices. Land M(n) fully — code + a
  runnable result + tests — before starting M(n+1).
- **Teaching is a deliverable.** When you introduce a remote-sensing concept for the first
  time, add a concise explanation in the module docstring and, where useful, a short
  `notebooks/` cell that visualizes it. The owner should learn the stack by reading your
  code.
- **Guard the owner's time and machine.** Before any large download or long compute
  (full-department, full-time-range), print the estimated data volume / runtime and
  default to the small AOI unless `--force` / explicit scale-up. Ask before doing anything
  that would pull tens of GB.
- **Verify as you go.** After each stage, produce a visual artifact (a saved PNG map or plot)
  so correctness is eyeball-checkable, and run the tests.
- When a pinned tool/data source misbehaves, **stop and report** with the exact error +
  a proposed fix; don't silently swap libraries or change the data backend.
- Keep `README.md` and `docs/glossary.md` updated as features land, not all at the end.
- Prefer clarity over cleverness — this code is read by recruiters as much as run.

First action: confirm the environment (`python --version`, `uv --version`), then execute
M0 and stop for review.

## 11. Post-v1 goal — ScruTech QGIS plugin (owner's end target)

**Owner's stated end goal (record — carry across sessions):** once the v1 pipeline
(M0–M8) is complete, integrate these treatments as an *automated pipeline inside a
QGIS plugin/extension named **ScruTech***. The pipeline stages (AOI → STAC search →
datacube → NDVI → monthly composites → MK/Sen trend → drought anomaly/VCI → zonal
→ outputs) should be drivable from QGIS, not only the CLI.

Design implications to keep in mind while building v1 (do not implement the plugin
until M0–M8 land, unless asked):

- Keep the science in pure, import-light functions (`indices`, `composite`, `trend`,
  `drought`, `zonal`) with **no CLI/Streamlit coupling**, so a QGIS Processing
  provider/algorithm can call them directly. This is already the convention (§7).
- Keep every stage parameterized through a plain config object, not argv — so a QGIS
  algorithm dialog can populate the same parameters.
- Outputs are standard GIS formats (GeoParquet, GeoTIFF/zarr, DuckDB) that QGIS reads.
- Mind QGIS's bundled Python: prefer widely-available deps; note any that would need
  a QGIS-side install (odc-stac, xarray, dask) when the plugin phase starts.
- Likely shape: a QGIS **Processing** plugin ("ScruTech") exposing one algorithm per
  stage plus a "run all" model, reusing `src/vegevigie` as the engine.
