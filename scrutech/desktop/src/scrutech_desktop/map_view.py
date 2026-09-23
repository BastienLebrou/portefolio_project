"""The map of the window: pick a zone, then read the results.

Leaflet in a web view, with the same basemaps as the report (plan and IGN aerial photos). The
extent of an analysis is simply what the map shows, so there is no bounding box to type. Once
a run is over, the very same view displays its HTML report, legends included.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

_ORTHO = (
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/jpeg"
    "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
)
_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{height:100%;margin:0;background:#F1E8D2}</style></head>
<body><div id="map"></div><script>
var map = L.map('map').setView([__LAT__, __LON__], __ZOOM__);
var plan = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(map);
var ortho = L.tileLayer('__ORTHO__', {maxZoom: 19, attribution: 'IGN Géoplateforme'});
L.control.layers({'Plan': plan, 'Photographies aériennes (IGN)': ortho}).addTo(map);
L.control.scale({imperial: false}).addTo(map);
</script></body></html>
"""


class MapView(QWebEngineView):
    """A Leaflet map whose current view is the study area."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.show_map()

    def show_map(self, centre: tuple[float, float] = (46.6, 2.5), zoom: int = 6) -> None:
        """Back to the pickable map (France by default)."""
        page = (
            _PAGE.replace("__LAT__", str(centre[0]))
            .replace("__LON__", str(centre[1]))
            .replace("__ZOOM__", str(zoom))
            .replace("__ORTHO__", _ORTHO)
        )
        self.setHtml(page, QUrl("https://scrutech.local/"))

    def show_file(self, path: str | Path) -> None:
        """Show a local HTML page (a run's report) in place of the map."""
        self.setUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def extent(self, callback) -> None:
        """Hand the visible extent to ``callback`` as (west, south, east, north)."""

        def parse(value) -> None:
            try:
                west, south, east, north = (float(v) for v in str(value).split(","))
            except (TypeError, ValueError):
                callback(None)
            else:
                callback((west, south, east, north))

        self.page().runJavaScript("map.getBounds().toBBoxString()", parse)
