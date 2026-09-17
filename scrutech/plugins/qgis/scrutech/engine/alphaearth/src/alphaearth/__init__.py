"""ScruTech AlphaEarth — Google satellite embeddings as a geospatial analysis engine.

Fetch 64-D annual embeddings from Earth Engine (:mod:`alphaearth.client`), cache them
in GeoParquet (:mod:`alphaearth.store`), classify land use with a Random Forest
(:mod:`alphaearth.classifier`), and detect year-over-year change by cosine distance
(:mod:`alphaearth.change`).
"""

from __future__ import annotations

from alphaearth._columns import EMB_COLS
from alphaearth.change import cosine_distance, detect_change
from alphaearth.classifier import TrainedModel, classify, train_classifier

__all__ = [
    "EMB_COLS",
    "TrainedModel",
    "classify",
    "cosine_distance",
    "detect_change",
    "train_classifier",
]
