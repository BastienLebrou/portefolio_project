# scrutech-core

Shared geodata core for the ScruTech pillars — the socle that ≥2 bricks use:

- `core.aoi` — `Aoi` + `resolve_aoi()` (AOI-first entry point: INSEE / dept / bbox /
  vector file / GeoDataFrame → normalized AOI). Commune boundaries via
  geo.api.gouv.fr (all départements), france-geojson mirror as fallback.
- `core.io` — `read_vector()` (the single multi-format vector reader) and
  `write_geoparquet()`.

Light deps only (geopandas, shapely, pyarrow, requests). Heavier concerns (DuckDB
store, COG writing) land here brick by brick as their first consumer arrives.
