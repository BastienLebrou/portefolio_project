"""Shared CRS constants and the bbox type alias."""

from __future__ import annotations

# Un CRS (Coordinate Reference System / système de coordonnées) dit comment des nombres
# (x, y) se traduisent en position réelle sur Terre. "EPSG:xxxx" est juste le numéro de
# code standard d'un CRS dans un registre international.
#
# WGS84 : coordonnées en longitude/latitude (degrés), le système utilisé par GPS, Google
# Maps, les API web (geo.api.gouv.fr, STAC...). Pratique pour échanger des données, mais
# les degrés ne sont pas des mètres : on ne peut pas calculer une distance ou une surface
# directement dessus sans se tromper (les degrés "rétrécissent" en s'éloignant de l'équateur).
WGS84 = "EPSG:4326"

# L93 (Lambert-93) : la projection officielle française, en mètres. Dès qu'on doit
# mesurer une distance, une surface, faire un buffer (zone tampon) ou une intersection
# géométrique fiable sur le territoire français, on reprojette en L93 d'abord.
L93 = "EPSG:2154"  # Lambert-93, metres

# Une "bounding box" (bbox) est le plus petit rectangle qui contient une géométrie :
# (minx, miny, maxx, maxy) = (longitude min, latitude min, longitude max, latitude max)
# en WGS84, ou (x min, y min, x max, y max) en mètres en L93. `tuple[float, float, float,
# float]` est juste un alias de type : ça documente qu'une variable de type `BBox`
# contient toujours exactement 4 nombres dans cet ordre.
BBox = tuple[float, float, float, float]
