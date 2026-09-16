"""ScruTech visual report: a self-contained HTML page summarising an area's analyses.

Reads whatever pillar outputs were cached for the area (VegeVigie, PAFF, écobuage, Biotrame,
AlphaEarth) and writes key figures, a map and plain-French sentences (see ``html``).
Generated on demand from QGIS and opened in the browser.
"""

from vegevigie.report.data import ReportInputs, discover

__all__ = ["ReportInputs", "discover"]
