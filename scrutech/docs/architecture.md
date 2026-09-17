# ScruTech Architecture

ScruTech is a geospatial analysis portfolio organized as a small Python monorepo.

## Repository layout

- `packages/`: installable Python packages. `core` is the shared AOI, I/O, storage, and DuckDB layer; `vegevigie` is the main orchestration package; `biotrame`, `alphaearth`, and `ecobuage` provide focused engines.
- `applications/`: standalone tools that are not part of the shared package dependency graph. Each application keeps its executable entry point and tests together.
- `plugins/`: distributable integrations. The QGIS plugin is built from `plugins/qgis` and bundles engine sources into its generated `scrutech/engine` directory.
- `data/setup/`: database schema and data acquisition/bootstrap utilities. Runtime data belongs outside version control and is selected with `SCRUTECH_DATA` where supported.
- `docs/`: cross-project technical documentation.
- `scripts/`: repository maintenance and portfolio-generation utilities.

## Dependency direction

The shared `core` package is the lowest-level geospatial dependency. Domain packages depend on it, while applications may use the packages or remain standalone. The QGIS plugin invokes heavy analysis in an external Python environment so QGIS's own GDAL stack is not modified.

## Naming policy

Python packages and modules use lowercase `snake_case`. Executable modules use a verb or a precise action, such as `run_pipeline.py`, `run_vacancy_analysis.py`, or `download_fiber_data.py`. Directory names use lowercase or kebab-case. Public Python import names remain `core`, `vegevigie`, `biotrame`, `alphaearth`, and `ecobuage` to preserve package compatibility.

## Validation

The main package test suite is configured in `packages/vegevigie/pyproject.toml` and covers the sibling packages. Standalone application tests run from their own directories because their flat-module import contracts are intentionally isolated.
