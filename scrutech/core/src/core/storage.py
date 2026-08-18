"""Where ScruTech products live — one layout, local first, S3 later.

The layout is identical on disk and (later) on S3, so switching is an env var:

    {SCRUTECH_DATA}/{pilier}/aoi={aoi_id}/{produit}/[{fenetre}/]fichier

e.g. ``vegevigie/aoi=insee-07005/trend/2018_2025/sen_slope.tif``. The queryable
side lives in a single DuckDB file next to it (see :mod:`core.db`); GeoParquet/COG
are the map layers, the DB holds stats, registry and lookups.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

ENV_ROOT = "SCRUTECH_DATA"
DB_FILENAME = "scrutech.duckdb"

# Extensions QGIS can load directly as map layers.
_LOADABLE = {".geojson", ".tif", ".tiff", ".gpkg", ".parquet"}


def data_root() -> Path:
    """Store root: ``$SCRUTECH_DATA`` if set, else ``<repo>/scrutech/data``."""
    root = os.environ.get(ENV_ROOT)
    if root:
        return Path(root)
    return Path(__file__).resolve().parents[3] / "data"


def db_path() -> Path:
    """The single central DuckDB file."""
    return data_root() / DB_FILENAME


def product_path(
    pilier: str,
    aoi_id: str,
    produit: str,
    fenetre: str | None = None,
    filename: str | None = None,
) -> Path:
    """Path of a product for one AOI — the one place that knows the layout.

    ``fenetre`` is an optional time window (e.g. ``"2018_2025"``); without
    ``filename`` you get the directory.
    """
    path = data_root() / pilier / f"aoi={aoi_id}" / produit
    if fenetre:
        path = path / fenetre
    return path / filename if filename else path


def cache_outputs(aoi_id: str, pilier: str, files: list[str | Path]) -> list[Path]:
    """Copy a run's output files (and any sibling ``.qml``) into the store, keyed by AOI.

    Lets a later session **load** the products instead of recomputing them. Destination:
    ``{SCRUTECH_DATA}/{pilier}/aoi={aoi_id}/output/<filename>``. Idempotent (overwrites).
    """
    dests: list[Path] = []
    for src in files:
        src = Path(src)
        if not src.exists():
            continue
        dest = product_path(pilier, aoi_id, "output", filename=src.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        qml = src.with_suffix(".qml")
        if qml.exists():
            shutil.copy2(qml, dest.with_suffix(".qml"))
        dests.append(dest)
    return dests


def list_cached(aoi_id: str) -> list[Path]:
    """Loadable cached products for an AOI across all pillars (map layers, deduped).

    Drops a ``.parquet`` when a same-named ``.geojson`` exists (same vector product), so the
    map isn't loaded twice.
    """
    root = data_root()
    hits = [p for p in root.glob(f"*/aoi={aoi_id}/output/*") if p.suffix.lower() in _LOADABLE]
    geojson_stems = {(p.parent, p.stem) for p in hits if p.suffix.lower() == ".geojson"}

    def _is_parquet_twin(p: Path) -> bool:
        return p.suffix.lower() == ".parquet" and (p.parent, p.stem) in geojson_stems

    return sorted(p for p in hits if not _is_parquet_twin(p))
