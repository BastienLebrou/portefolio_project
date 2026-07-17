"""Where ScruTech products live — one layout, local first, S3 later.

The layout is identical on disk and (later) on S3, so switching is an env var:

    {SCRUTECH_DATA}/{pilier}/aoi={aoi_id}/{produit}/[{fenetre}/]fichier

e.g. ``vegevigie/aoi=insee-07005/trend/2018_2025/sen_slope.tif``. The queryable
side lives in a single DuckDB file next to it (see :mod:`core.db`); GeoParquet/COG
are the map layers, the DB holds stats, registry and lookups.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ROOT = "SCRUTECH_DATA"
DB_FILENAME = "scrutech.duckdb"


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
