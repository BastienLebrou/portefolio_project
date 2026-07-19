"""Enum access that works on QGIS 3.x **and** QGIS 4.

QGIS 4 moves enum members onto scoped enums (``Qgis.WkbType.MultiPolygon``,
``QgsProcessingParameterNumber.Type.Double``…) where 3.x exposed them directly on the
class. Each constant below prefers the scoped form when it exists and falls back to the
3.x one, so the algorithms stay readable and load on both majors.
"""

from __future__ import annotations

from typing import Any

from qgis.core import (
    QgsFeatureSink,
    QgsProcessing,
    QgsProcessingParameterFile,
    QgsProcessingParameterNumber,
    QgsWkbTypes,
)

try:  # scoped enums live on Qgis (QGIS >= 3.36, required in 4.x)
    from qgis.core import Qgis
except ImportError:  # pragma: no cover — very old QGIS
    Qgis = None  # type: ignore[assignment]


def _scoped_or(owner: Any, scope: str, name: str) -> Any:
    """``owner.scope.name`` if that scope exists, else ``owner.name`` (QGIS 3 style)."""
    return getattr(getattr(owner, scope, owner), name)


def _from_qgis(scope: str, new_name: str, fallback_owner: Any, old_name: str) -> Any:
    """``Qgis.scope.new_name`` when available, else the QGIS 3 unscoped member."""
    enum = getattr(Qgis, scope, None) if Qgis is not None else None
    if enum is not None and hasattr(enum, new_name):
        return getattr(enum, new_name)
    return getattr(fallback_owner, old_name)


# Parameter enums.
NUMBER_INTEGER = _scoped_or(QgsProcessingParameterNumber, "Type", "Integer")
NUMBER_DOUBLE = _scoped_or(QgsProcessingParameterNumber, "Type", "Double")
FILE_BEHAVIOR_FILE = _scoped_or(QgsProcessingParameterFile, "Behavior", "File")
SINK_FAST_INSERT = _scoped_or(QgsFeatureSink, "Flag", "FastInsert")

# Layer/geometry type enums (renamed, not just re-scoped, in QGIS 4).
SOURCE_VECTOR_POLYGON = _from_qgis(
    "ProcessingSourceType", "VectorPolygon", QgsProcessing, "TypeVectorPolygon"
)
SOURCE_VECTOR_LINE = _from_qgis(
    "ProcessingSourceType", "VectorLine", QgsProcessing, "TypeVectorLine"
)
WKB_MULTILINESTRING = _from_qgis("WkbType", "MultiLineString", QgsWkbTypes, "MultiLineString")
WKB_MULTIPOLYGON = _from_qgis("WkbType", "MultiPolygon", QgsWkbTypes, "MultiPolygon")
