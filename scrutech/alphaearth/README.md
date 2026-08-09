# scrutech-alphaearth

AlphaEarth (Google DeepMind satellite embeddings) as a ScruTech analysis engine.

- `alphaearth.client` — GEE fetch of `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` (auth via
  QgsAuthManager, cost estimate). AlphaEarth is served **only** on Earth Engine.
- `alphaearth.store` — GeoParquet cache per (AOI, year), idempotent, with provenance.
- `alphaearth.classifier` — Random Forest on the 64 embedding features (50-200 labels
  suffice); cross-validation is mandatory.
- `alphaearth.change` — cosine distance between two years (a real surface change, not an
  atmospheric artefact — the break vs the NDVI-before/after v1).

Heavy deps (`earthengine-api`, `scikit-learn`) — this is an **optional** ScruTech pillar,
run in the external interpreter, not in QGIS's Python.

## Limits (honest)
Annual only (no monthly), 10 m (zones > 1 ha), academic access deadline to track. The RF
is a shallow classifier on rich features — **not** a foundation model itself.
