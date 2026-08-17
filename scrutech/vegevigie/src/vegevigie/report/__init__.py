"""ScruTech visual report — a Streamlit page summarising an analysis output folder.

Reads whatever pillar outputs a run produced (biotrame hexagons, écobuage rasters,
VegeVigie trend/drought, PAF interface, AlphaEarth change) and renders them on one map
with metrics and charts. Launched on demand from QGIS (opens in the browser).
"""

from vegevigie.report.data import ReportInputs, discover

__all__ = ["ReportInputs", "discover"]
