"""ScruTech — QGIS plugin entry point.

QGIS calls :func:`classFactory` when loading the plugin. Kept import-light so a
missing datacube dependency can't stop the plugin from loading (it's checked
lazily when an algorithm actually runs).
"""

from __future__ import annotations


def classFactory(iface):  # noqa: N802 — QGIS-mandated name
    from .scrutech_plugin import ScruTechPlugin

    return ScruTechPlugin(iface)
