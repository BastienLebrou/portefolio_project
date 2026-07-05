# VegeVigie

*VegeVigie — sentinelle de la végétation. NDVI trends & drought stress from Sentinel-2,
commune by commune.*

A reproducible geodata-engineering pipeline that watches vegetation health over time from
Sentinel-2 imagery: NDVI time series, statistically significant greening/browning trends
(Mann-Kendall + Sen's slope), and drought-stress flags — aggregated to the commune level
for the Ardèche département and served through a small dashboard.

> **Status: M0 (scaffold).** The CLI is wired, config is validated, lint/tests/CI are green.
> Pipeline stages land milestone by milestone — see `CLAUDE.md` §6 for the roadmap.
> The full portfolio README (hero images, architecture diagram, methodology) is the M8
> deliverable.

## Quickstart

```bash
cd vegevigie
uv sync
uv run vegevigie --help
```

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
uv run pre-commit install   # once, to lint on every commit
```
