"""The ScruTech QML styles, shared with the engine and the desktop app.

The real code lives in ``vegevigie.styles`` (pure strings, no QGIS import), bundled flat next to
the plugin by ``package.py`` as ``scrutech_styles`` so QGIS can import it without the engine
stack. This module keeps the name the algorithms already use.
"""

from __future__ import annotations

from scrutech_styles import (  # noqa: F401 — re-exported for the algorithms
    biotrame_qml,
    break_year_qml,
    drought_qml,
    ecobuage_aptitude_qml,
    ecobuage_classes_qml,
    exposure_qml,
    ndvi_projection_qml,
    paff_line_qml,
    paff_zone_qml,
    report_styles,
    stress_frequency_qml,
    style_for,
    trend_class_qml,
    trend_qml,
)
