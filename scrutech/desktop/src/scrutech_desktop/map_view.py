"""The map of the window: pick a zone, then read the results.

Leaflet in a web view. The study area is a rectangle: drawn with the mouse, taken from a
commune outline, or typed in the form — and when none is set, simply what the map shows. Four
basemaps and the cadastral parcels are one click away, and once a run is over the very same
view displays its HTML report, legends included.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView

_GEOPF = (
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER={layer}&STYLE=normal&TILEMATRIXSET=PM&FORMAT={fmt}"
    "&TILEMATRIX={{z}}&TILEROW={{y}}&TILECOL={{x}}"
)
_ORTHO = _GEOPF.format(layer="ORTHOIMAGERY.ORTHOPHOTOS", fmt="image/jpeg")
_PLAN_IGN = _GEOPF.format(layer="GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", fmt="image/png")
_CADASTRE = _GEOPF.format(layer="CADASTRALPARCELS.PARCELLAIRE_EXPRESS", fmt="image/png")

_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>html,body,#map{height:100%;margin:0;background:#F1E8D2}
.leaflet-container.drawing{cursor:crosshair}</style></head>
<body><div id="map"></div><script>
var map = L.map('map').setView([__LAT__, __LON__], __ZOOM__);
var bases = {
  'Plan (OpenStreetMap)': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom: 19, attribution: '© OpenStreetMap'}),
  'Plan IGN': L.tileLayer('__PLAN_IGN__', {maxZoom: 19, attribution: 'IGN Géoplateforme'}),
  'Photographies aériennes (IGN)': L.tileLayer('__ORTHO__',
    {maxZoom: 19, attribution: 'IGN Géoplateforme'}),
  'Relief (OpenTopoMap)': L.tileLayer('https://a.tile.opentopomap.org/{z}/{x}/{y}.png',
    {maxZoom: 17, attribution: '© OpenTopoMap'})
};
bases['__BASE__'].addTo(map);
var cadastre = L.tileLayer('__CADASTRE__', {maxZoom: 19, opacity: 0.8,
  attribution: 'IGN Géoplateforme'});
L.control.layers(bases, {'Parcelles cadastrales (IGN)': cadastre}).addTo(map);
L.control.scale({imperial: false}).addTo(map);

var zone = null, outline = null, drawing = false, origin = null;

function setZone(w, s, e, n, fit) {
  if (zone) { map.removeLayer(zone); }
  zone = L.rectangle([[s, w], [n, e]],
    {color: '#661C1A', weight: 2, fillColor: '#B23F2C', fillOpacity: 0.12}).addTo(map);
  if (fit) { map.fitBounds(zone.getBounds(), {padding: [24, 24]}); }
}

function clearZone() {
  if (zone) { map.removeLayer(zone); zone = null; }
  if (outline) { map.removeLayer(outline); outline = null; }
}

function showCommune(geometry) {
  clearZone();
  outline = L.geoJSON(geometry,
    {style: {color: '#5C6A30', weight: 2, fillOpacity: 0.05, dashArray: '4 3'}}).addTo(map);
  var b = outline.getBounds();
  setZone(b.getWest(), b.getSouth(), b.getEast(), b.getNorth(), true);
}

function zoneBBox() {
  return (zone ? zone.getBounds() : map.getBounds()).toBBoxString();
}

function startDraw() {
  drawing = true;
  map.dragging.disable();
  L.DomUtil.addClass(map.getContainer(), 'drawing');
}

map.on('mousedown', function (ev) {
  if (!drawing) { return; }
  origin = ev.latlng;
  if (outline) { map.removeLayer(outline); outline = null; }
  setZone(origin.lng, origin.lat, origin.lng, origin.lat, false);
});
map.on('mousemove', function (ev) {
  if (drawing && origin) { zone.setBounds(L.latLngBounds(origin, ev.latlng)); }
});
map.on('mouseup', function () {
  if (!drawing) { return; }
  drawing = false; origin = null;
  map.dragging.enable();
  L.DomUtil.removeClass(map.getContainer(), 'drawing');
});
</script></body></html>
"""


class MapView(QWebEngineView):
    """A Leaflet map whose rectangle — or whose view, by default — is the study area."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.basemap = "Plan (OpenStreetMap)"
        self.show_map()

    def show_map(self, centre: tuple[float, float] = (46.6, 2.5), zoom: int = 6) -> None:
        """Back to the pickable map (France by default)."""
        page = (
            _PAGE.replace("__LAT__", str(centre[0]))
            .replace("__LON__", str(centre[1]))
            .replace("__ZOOM__", str(zoom))
            .replace("__ORTHO__", _ORTHO)
            .replace("__PLAN_IGN__", _PLAN_IGN)
            .replace("__CADASTRE__", _CADASTRE)
            .replace("__BASE__", self.basemap)
        )
        self.setHtml(page, QUrl("https://scrutech.local/"))

    def set_basemap(self, name: str) -> None:
        """Choose the background of the map; kept for the next runs."""
        self.basemap = name
        self._js(f"Object.keys(bases).forEach(function (k) {{ map.removeLayer(bases[k]); }});"
                 f"bases[{json.dumps(name)}].addTo(map);")

    def show_file(self, path: str | Path) -> None:
        """Show a local HTML page (a run's report) in place of the map."""
        self.setUrl(QUrl.fromLocalFile(str(Path(path).resolve())))

    def set_zone(self, bbox: tuple[float, float, float, float], fit: bool = True) -> None:
        """Draw the study rectangle from west, south, east, north."""
        west, south, east, north = bbox
        self._js(f"setZone({west}, {south}, {east}, {north}, {'true' if fit else 'false'})")

    def clear_zone(self) -> None:
        """Forget the rectangle: the visible view becomes the study area again."""
        self._js("clearZone()")

    def start_draw(self) -> None:
        """Next mouse drag draws the study rectangle."""
        self._js("startDraw()")

    def show_commune(self, geometry: dict) -> None:
        """Outline a commune and take its bounding box as the study area."""
        self._js(f"showCommune({json.dumps(geometry)})")

    def extent(self, callback) -> None:
        """Hand the study area to ``callback`` as (west, south, east, north)."""

        def parse(value) -> None:
            try:
                west, south, east, north = (float(v) for v in str(value).split(","))
            except (TypeError, ValueError):
                callback(None)
            else:
                callback((west, south, east, north))

        self.page().runJavaScript("zoneBBox()", parse)

    def _js(self, script: str) -> None:
        self.page().runJavaScript(script)
