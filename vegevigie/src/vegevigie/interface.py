"""Wildland-Urban Interface (WUI) — the forest↔built-up frontier for the PAFF layer.

The single most fire-critical geometry is neither the forest nor the houses, but the
*line where they meet*: the Wildland-Urban Interface. Embers, radiant heat and the
French légal débroussaillement obligation (OLD, 50 m) all act in a narrow band
straddling that line. This stage turns two input layers — forest zones (typically
VegeVigie-classified vulnerable vegetation) and built-up zones — into the products
the PAFF loop needs, clipped to an area of interest:

- ``interface_line`` — the forest boundary segments that run within ``contact_m`` of a
  building: the frontier itself;
- ``interface_zone`` — the forest band within ``contact_m`` of built-up areas: the
  vegetation that threatens (and is threatened by) the houses. This is both the OLD
  débroussaillement footprint and the PAFF's priority target zone;
- summary metrics — frontier length, band area, built-up area exposed.

All distance/area maths run in a projected CRS (Lambert-93 by default); inputs in any
CRS are reprojected first. Pure geometry — no I/O here (that lives in
:func:`build_interface`), so the maths is unit-testable offline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
from shapely.geometry import base as shp_base
from shapely.geometry import box

logger = logging.getLogger("vegevigie")

WGS84 = "EPSG:4326"


@dataclass(frozen=True)
class InterfaceResult:
    """The three WUI products: two layers (in the metric CRS) plus scalar metrics."""

    line: gpd.GeoDataFrame
    zone: gpd.GeoDataFrame
    metrics: dict[str, float]


def _clip_geom(layer: gpd.GeoDataFrame, aoi: shp_base.BaseGeometry | None) -> gpd.GeoDataFrame:
    """Return the features of ``layer`` intersecting ``aoi`` (or all if ``aoi`` is None)."""
    if aoi is None:
        return layer
    return layer[layer.intersects(aoi)].copy()


def forest_bati_interface(
    forest: gpd.GeoDataFrame,
    bati: gpd.GeoDataFrame,
    metric_crs: str,
    contact_m: float,
    aoi: gpd.GeoDataFrame | shp_base.BaseGeometry | None = None,
) -> InterfaceResult:
    """Compute the forest↔built-up interface line and band within ``contact_m``.

    Both layers are reprojected to ``metric_crs`` and, if ``aoi`` is given, restricted
    to features overlapping it. The frontier is the part of the forest outline lying
    within ``contact_m`` of any building; the band is the forest area within that same
    distance — the vegetation the PAFF must defend. Returns empty geometries (and zero
    metrics) when the two layers never come within ``contact_m`` of each other.
    """
    forest_m = forest.to_crs(metric_crs)
    bati_m = bati.to_crs(metric_crs)

    aoi_geom: shp_base.BaseGeometry | None = None
    if aoi is not None:
        aoi_gdf = aoi if isinstance(aoi, gpd.GeoDataFrame) else gpd.GeoSeries([aoi], crs=metric_crs)
        aoi_geom = aoi_gdf.to_crs(metric_crs).union_all()
        forest_m = _clip_geom(forest_m, aoi_geom)
        bati_m = _clip_geom(bati_m, aoi_geom)

    if forest_m.empty or bati_m.empty:
        logger.warning("Forest or bâti layer is empty within the AOI — no interface to compute.")
        return _empty_result(metric_crs)

    forest_u = forest_m.union_all()
    bati_u = bati_m.union_all()
    if aoi_geom is not None:  # honour the emprise exactly, not just at the feature level
        forest_u = forest_u.intersection(aoi_geom)
        bati_u = bati_u.intersection(aoi_geom)

    reach = bati_u.buffer(contact_m)
    line = forest_u.boundary.intersection(reach)
    zone = forest_u.intersection(reach)

    metrics = {
        "contact_m": float(contact_m),
        "interface_length_m": float(line.length),
        "interface_zone_ha": float(zone.area) / 10_000.0,
        "bati_area_ha": float(bati_u.area) / 10_000.0,
    }
    logger.info(
        "Interface: %.0f m of frontier, %.1f ha of band to treat (contact %.0f m).",
        metrics["interface_length_m"],
        metrics["interface_zone_ha"],
        contact_m,
    )

    line_gdf = gpd.GeoDataFrame({"kind": ["interface_line"]}, geometry=[line], crs=metric_crs)
    zone_gdf = gpd.GeoDataFrame(
        {"kind": ["interface_zone"], "area_ha": [metrics["interface_zone_ha"]]},
        geometry=[zone],
        crs=metric_crs,
    )
    return InterfaceResult(line=line_gdf, zone=zone_gdf, metrics=metrics)


def _empty_result(metric_crs: str) -> InterfaceResult:
    empty = gpd.GeoDataFrame({"kind": []}, geometry=[], crs=metric_crs)
    metrics = {
        "contact_m": 0.0,
        "interface_length_m": 0.0,
        "interface_zone_ha": 0.0,
        "bati_area_ha": 0.0,
    }
    return InterfaceResult(line=empty, zone=empty.copy(), metrics=metrics)


def _read_layer(path: Path) -> gpd.GeoDataFrame:
    """Read any vector layer — GeoParquet by suffix, else GDAL/pyogrio (gpkg/shp/geojson)."""
    if path.suffix.lower() == ".parquet":
        return gpd.read_parquet(path)
    return gpd.read_file(path)


def _load_aoi(
    aoi_path: Path | None, bbox: tuple[float, float, float, float] | None, metric_crs: str
) -> gpd.GeoDataFrame | shp_base.BaseGeometry | None:
    """Build the AOI from an explicit layer (any CRS) or a ``metric_crs`` bbox, or None."""
    if aoi_path is not None:
        return _read_layer(aoi_path)
    if bbox is not None:
        return gpd.GeoDataFrame(geometry=[box(*bbox)], crs=metric_crs)
    return None


def build_interface(
    forest_path: Path,
    bati_path: Path,
    out_dir: Path,
    metric_crs: str,
    contact_m: float,
    aoi_path: Path | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    force: bool = False,
) -> tuple[Path, Path, dict[str, float]]:
    """Read the two layers, compute the WUI, and write GeoParquet + WGS84 GeoJSON.

    Outputs land in ``out_dir``: ``interface_line`` / ``interface_zone`` as ``.parquet``
    (metric CRS, for QGIS/GeoPandas) and ``.geojson`` (WGS84, for the deck.gl/MapLibre
    front). ``bbox`` is interpreted in ``metric_crs`` (the QGIS canvas extent case);
    ``aoi_path`` may be in any CRS. Idempotent unless ``force``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    line_parquet = out_dir / "interface_line.parquet"
    zone_parquet = out_dir / "interface_zone.parquet"
    if line_parquet.exists() and zone_parquet.exists() and not force:
        logger.info("Interface outputs already present in %s; use force to rebuild.", out_dir)
        return line_parquet, zone_parquet, {}

    forest = _read_layer(forest_path)
    bati = _read_layer(bati_path)
    aoi = _load_aoi(aoi_path, bbox, metric_crs)

    result = forest_bati_interface(forest, bati, metric_crs, contact_m, aoi)

    result.line.to_parquet(line_parquet)
    result.zone.to_parquet(zone_parquet)
    result.line.to_crs(WGS84).to_file(out_dir / "interface_line.geojson", driver="GeoJSON")
    result.zone.to_crs(WGS84).to_file(out_dir / "interface_zone.geojson", driver="GeoJSON")

    logger.info("Wrote interface layers to %s (+ WGS84 GeoJSON exports).", out_dir)
    return line_parquet, zone_parquet, result.metrics
