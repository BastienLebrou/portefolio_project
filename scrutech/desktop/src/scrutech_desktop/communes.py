"""Find a commune by name: the study area of most analyses, in two words typed.

Uses the French government's open API (geo.api.gouv.fr), through the standard library only,
and hands back the outline so the map can show exactly what will be analysed.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://geo.api.gouv.fr/communes"
_FIELDS = "nom,code,codesPostaux,population,departement,contour"


@dataclass(frozen=True)
class Commune:
    """One commune: how to name it, where it is, and its outline."""

    name: str
    code: str
    department: str
    population: int
    contour: dict  # GeoJSON geometry (WGS84)

    @property
    def label(self) -> str:
        people = f"{self.population:,}".replace(",", " ")
        return f"{self.name} ({self.department}) · {people} hab."

    def bbox(self) -> tuple[float, float, float, float]:
        """West, south, east, north of the outline."""
        lons, lats = zip(*_points(self.contour), strict=True)
        return min(lons), min(lats), max(lons), max(lats)


def search(name: str, limit: int = 8, timeout: int = 20) -> list[Commune]:
    """The communes whose name matches, most populated first ([] when nothing matches)."""
    query = urllib.parse.urlencode(
        {"nom": name.strip(), "fields": _FIELDS, "limit": limit, "boost": "population"}
    )
    with urllib.request.urlopen(f"{API}?{query}", timeout=timeout) as response:  # noqa: S310
        return parse(json.loads(response.read().decode("utf-8")))


def parse(payload: list[dict]) -> list[Commune]:
    """Turn the API answer into communes, skipping those without an outline."""
    out = []
    for item in payload:
        contour = item.get("contour")
        if not contour:
            continue
        department = (item.get("departement") or {}).get("nom", "")
        out.append(
            Commune(
                name=item.get("nom", ""),
                code=item.get("code", ""),
                department=department,
                population=int(item.get("population") or 0),
                contour=contour,
            )
        )
    return out


def _points(geometry: dict):
    """Every (lon, lat) of a GeoJSON Polygon or MultiPolygon."""
    coordinates = geometry.get("coordinates", [])
    if geometry.get("type") == "Polygon":
        rings = coordinates
    else:
        rings = [ring for polygon in coordinates for ring in polygon]
    for ring in rings:
        for point in ring:
            yield point[0], point[1]
