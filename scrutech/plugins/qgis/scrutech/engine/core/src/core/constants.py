"""Shared CRS constants and the bbox type alias."""

from __future__ import annotations

WGS84 = "EPSG:4326"
L93 = "EPSG:2154"  # Lambert-93, metres

# (minx, miny, maxx, maxy)
BBox = tuple[float, float, float, float]
