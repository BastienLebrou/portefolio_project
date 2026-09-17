"""H3 hexagonal tessellation of an AOI — the grid every biotrame indicator aggregates onto.

CE QUE ÇA FAIT : découpe une emprise en hexagones H3 (grille régulière mondiale de Uber).
Chaque hexagone recevra ensuite ses scores croisés (enjeu / dégradation / connectivité).

POURQUOI H3 et non une grille carrée : les hexagones ont 6 voisins équidistants (pas de
diagonale ambiguë), ce qui rend l'analyse de connectivité et de voisinage cohérente — la
bonne maille pour raisonner « corridors » et « réservoirs ».
"""

from __future__ import annotations

import geopandas as gpd
import h3
from core.aoi import resolve_aoi
from core.constants import WGS84
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

# Indicative H3 cell sizes: r7 ≈ 5 km², r8 ≈ 0.7 km², r9 ≈ 0.1 km². Default r8 (fine commune).
DEFAULT_RESOLUTION = 8


def hex_grid(aoi: object, resolution: int = DEFAULT_RESOLUTION) -> gpd.GeoDataFrame:
    """Hexagons (WGS84) covering the AOI, columns ``hex_id`` + geometry.

    Uses H3 ``polygon_to_cells`` (a cell is kept if its centre falls in the AOI); for a tiny
    AOI that catches no centre, falls back to the single cell containing the AOI centroid.
    """
    a = resolve_aoi(aoi)
    cells = _cells_for_geometry(a.geom, resolution)
    if not cells:
        # Cas limite : une AOI si petite qu'aucun centre d'hexagone ne tombe dedans (plus
        # petite qu'une cellule H3 à cette résolution). On force au moins UN hexagone :
        # celui qui contient le centre de l'AOI, pour ne jamais renvoyer une grille vide.
        c = a.geom.centroid
        cells = [h3.latlng_to_cell(c.y, c.x, resolution)]
    polys = [_cell_polygon(c) for c in cells]
    return gpd.GeoDataFrame({"hex_id": cells}, geometry=polys, crs=WGS84)


def _cells_for_geometry(geom: BaseGeometry, resolution: int) -> list[str]:
    """All H3 cell ids whose centre falls within ``geom`` (Polygon or MultiPolygon)."""
    # Un MultiPolygon est une géométrie composée de PLUSIEURS polygones séparés (ex: une
    # zone d'étude avec deux îlots disjoints) ; .geoms les liste. Un Polygon simple n'a
    # pas cet attribut, donc on le met dans une liste à un seul élément pour traiter les
    # deux cas avec la même boucle.
    parts = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    # un set évite les hexagones en double si les polygones se touchent
    cells: set[str] = set()
    for part in parts:
        # H3 wants (lat, lng) rings; shapely coords are (lng, lat).
        # `.exterior` = le contour extérieur du polygone ; `.interiors` = ses éventuels
        # "trous" (des zones exclues à l'intérieur, comme un lac au milieu d'une forêt).
        outer = [(lat, lng) for lng, lat in part.exterior.coords]
        holes = [[(lat, lng) for lng, lat in ring.coords] for ring in part.interiors]
        poly = h3.LatLngPoly(outer, *holes)
        # polygon_to_cells fait tout le travail : trouve tous les hexagones H3 de cette
        # résolution dont le centre tombe dans le polygone.
        cells.update(h3.polygon_to_cells(poly, resolution))
    return sorted(cells)


def _cell_polygon(cell: str) -> Polygon:
    """The hexagon geometry of an H3 cell as a WGS84 shapely Polygon."""
    boundary = h3.cell_to_boundary(cell)  # [(lat, lng), ...]
    # On inverse à nouveau l'ordre des coordonnées : H3 raisonne en (lat, lng), shapely
    # (et tout le reste de ScruTech) attend (lng, lat) = (x, y).
    return Polygon([(lng, lat) for lat, lng in boundary])
