"""Area-of-interest resolution — the AOI-first entry point.

``resolve_aoi`` normalizes anything an algorithm might receive (INSEE code,
département, bbox, vector file, GeoDataFrame) into an :class:`Aoi`: a stable id, a
WGS84 geometry and a bbox. Every pillar keys its products on ``aoi_id``.

Commune boundaries come from geo.api.gouv.fr (all départements — fixes the old
Ardèche-only limitation), with the community france-geojson mirror as a fallback.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from core.constants import L93, WGS84, BBox

logger = logging.getLogger("scrutech")

GEOAPI = "https://geo.api.gouv.fr"
_MIRROR = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/departements"
# france-geojson fallback covers only a few départements (geo.api is the primary source).
_DEPT_SLUGS = {"07": "07-ardeche"}
_GEOJSON_FIELDS = {"fields": "code,nom,contour", "format": "geojson", "geometry": "contour"}


@dataclass(frozen=True)
class Aoi:
    """Normalized area of interest (geometry in WGS84)."""

    aoi_id: str
    label: str
    kind: str  # insee | dept | bbox | file | gdf
    geom: BaseGeometry
    bbox_wgs84: BBox

    def to_gdf(self) -> gpd.GeoDataFrame:
        """The AOI as a one-row WGS84 GeoDataFrame."""
        return gpd.GeoDataFrame({"aoi_id": [self.aoi_id]}, geometry=[self.geom], crs=WGS84)

    def to_l93(self) -> BaseGeometry:
        """The AOI geometry reprojected to Lambert-93 (metres)."""
        return self.to_gdf().to_crs(L93).geometry.iloc[0]


def resolve_aoi(aoi: object) -> Aoi:
    """Normalize an AOI input into an :class:`Aoi` (see module docstring)."""
    if isinstance(aoi, Aoi):
        return aoi
    if isinstance(aoi, gpd.GeoDataFrame):
        geom = aoi.to_crs(WGS84).union_all()
        return _from_geom(geom, "gdf", "gdf-" + _hash(geom.wkb), "GeoDataFrame")
    if isinstance(aoi, (tuple, list)) and len(aoi) == 4 and all(_is_num(v) for v in aoi):
        b: BBox = tuple(float(v) for v in aoi)  # type: ignore[assignment]
        return _from_geom(box(*b), "bbox", "bbox-" + "_".join(f"{c:.4f}" for c in b), "bbox")
    if isinstance(aoi, (str, Path)):
        return _resolve_str(str(aoi))
    raise ValueError(
        f"Cannot resolve AOI from {aoi!r}: expected 'insee:XXXXX', 'dept:XX', a bbox "
        "(minx,miny,maxx,maxy), a vector file path, or a GeoDataFrame."
    )


def fetch_communes(dept: str, timeout: int = 60) -> gpd.GeoDataFrame:
    """All commune polygons of a département (WGS84), columns code/nom/geometry.

    geo.api.gouv.fr first (any département); france-geojson mirror as fallback.
    """
    try:
        params = {"codeDepartement": dept, **_GEOJSON_FIELDS}
        feats = _get_json(f"{GEOAPI}/communes", params, timeout)["features"]
        gdf = gpd.GeoDataFrame.from_features(feats, crs=WGS84)
    except Exception as exc:  # noqa: BLE001 — any failure -> try the static mirror
        logger.warning("geo.api communes failed for %s (%s); trying mirror", dept, exc)
        gdf = _fetch_communes_mirror(dept, timeout)
    return gdf[["code", "nom", "geometry"]]


def fetch_commune(insee: str, timeout: int = 60) -> gpd.GeoDataFrame:
    """A single commune contour (WGS84) by INSEE code, columns code/nom/geometry."""
    gj = _get_json(f"{GEOAPI}/communes/{insee}", _GEOJSON_FIELDS, timeout)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    return gpd.GeoDataFrame.from_features(feats, crs=WGS84)[["code", "nom", "geometry"]]


def _resolve_str(s: str) -> Aoi:
    if s.startswith("insee:"):
        insee = s.split(":", 1)[1]
        geom = fetch_commune(insee).to_crs(WGS84).union_all()
        return _from_geom(geom, "insee", f"insee-{insee}", f"commune {insee}")
    if s.startswith("dept:"):
        dept = s.split(":", 1)[1]
        geom = fetch_communes(dept).to_crs(WGS84).union_all()
        return _from_geom(geom, "dept", f"dept-{dept}", f"departement {dept}")
    p = Path(s)
    if p.exists():
        from core.io import read_vector

        geom = read_vector(p).to_crs(WGS84).union_all()
        return _from_geom(geom, "file", f"file-{p.stem}", p.stem)
    raise ValueError(f"AOI string {s!r} is neither 'insee:'/'dept:' nor an existing file path.")


def _from_geom(geom: BaseGeometry, kind: str, aoi_id: str, label: str) -> Aoi:
    b: BBox = tuple(round(float(v), 6) for v in geom.bounds)  # type: ignore[assignment]
    return Aoi(aoi_id=aoi_id, label=label, kind=kind, geom=geom, bbox_wgs84=b)


def _hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:10]


def _is_num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _get_json(url: str, params: dict, timeout: int) -> dict:
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fetch_communes_mirror(dept: str, timeout: int) -> gpd.GeoDataFrame:
    try:
        slug = _DEPT_SLUGS[dept]
    except KeyError as exc:
        known = ", ".join(sorted(_DEPT_SLUGS))
        msg = (
            f"No france-geojson mirror slug for departement {dept!r} (known: {known}); "
            "geo.api.gouv.fr is the primary source."
        )
        raise KeyError(msg) from exc
    url = f"{_MIRROR}/{slug}/communes-{slug}.geojson"
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return gpd.GeoDataFrame.from_features(resp.json()["features"], crs=WGS84)
