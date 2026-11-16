"""Biodiag: desk-based biodiversity diagnostic of a project footprint.

GBIF occurrences around an emprise, crossed with protected areas (INPN) and protection / solar
sensitivity status, give stakes per species, a "reservoir or dent creuse" reading of the site
and an ecologist-style report (Markdown + PDF + interactive map). No field survey: it tells you
what the literature already says and where a targeted inventory is needed.
"""

from biodiag.biodiag_aoi import run_biodiag

__all__ = ["run_biodiag"]
