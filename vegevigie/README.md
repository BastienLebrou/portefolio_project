# VegeVigie

*VegeVigie — sentinelle de la végétation. NDVI trends & drought stress from Sentinel-2,
commune by commune.*

A reproducible geodata-engineering pipeline that watches vegetation health over time from
Sentinel-2 imagery: NDVI time series, statistically significant greening/browning trends
(Mann-Kendall + Sen's slope), and drought-stress flags — aggregated to the commune level
for the Ardèche département and served through a small dashboard.

> **Status: M4 (trend — the headline).** `aoi`/`search` build the footprint and Sentinel-2
> item list; `cube` loads a lazy (Red, NIR, SCL) datacube via odc-stac; `ndvi` does SCL
> masking + NDVI + gap-aware monthly composites; `trend` runs a vectorized, NaN-aware
> per-pixel Mann-Kendall + Theil–Sen (validated against `pymannkendall`) into a
> greening/browning raster. Config is validated, lint/mypy/tests/CI are green. Later stages
> land milestone by milestone — see `CLAUDE.md` §6. Full portfolio README is M8.

![AOI preview](docs/aoi_preview.png)

*Smoke-test AOI: 15 communes of southern Ardèche (incl. Alba-la-Romaine) inside the
default bbox, over the full département outline.*

![NDVI masking demo](docs/ndvi_masking_demo.png)

*SCL cloud masking (synthetic demo — real scene pending network egress): raw NDVI with
clouds/shadow → SCL classes → masked NDVI with flagged pixels blanked. Regenerate with
`uv run python scripts/demo_ndvi_masking.py`.*

![Monthly NDVI time series](docs/monthly_ndvi_timeseries.png)

*Gap-aware monthly compositing (synthetic demo): irregular cloud-masked scenes → a clean
monthly median line, with short gaps interpolated and a genuine winter data gap left
unfilled. Regenerate with `uv run python scripts/demo_monthly_ndvi.py`.*

![Trend map](docs/trend_map_demo.png)

*Per-pixel Mann-Kendall + Sen's slope (synthetic cube, real trend code): Sen's slope map
and the significant greening/browning class map. Regenerate with
`uv run python scripts/demo_trend_map.py`.*

## Quickstart

```bash
cd vegevigie
uv sync
uv run vegevigie --help

# M1 — build the AOI and search for scenes (small bbox, one year)
uv run vegevigie aoi --small
uv run vegevigie search --small --start 2020 --end 2020

# M2/M3 — datacube, then SCL-mask + NDVI + monthly composites (needs search cache)
uv run vegevigie cube --start 2020 --end 2020
uv run vegevigie ndvi --start 2020 --end 2020

# M4 — per-pixel Mann-Kendall + Sen's slope trend raster (needs monthly composites)
uv run vegevigie trend --start 2020 --end 2020
```

> **Network note.** `search` needs outbound access to
> `planetarycomputer.microsoft.com`. Under a restricted egress policy it reports the
> blocked host and exits cleanly — allowlist that host (or run outside the sandbox) to
> fetch scenes. The boundary source (`aoi`) uses the reachable `france-geojson` mirror of
> official IGN data; see `src/vegevigie/aoi.py`.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run pre-commit install   # once, to lint on every commit
```
