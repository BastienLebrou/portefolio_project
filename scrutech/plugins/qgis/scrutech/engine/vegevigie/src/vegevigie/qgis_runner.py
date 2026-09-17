"""Subprocess entry point so the QGIS plugin can run the pipeline out-of-process.

QGIS ships its own Python without the datacube stack, and installing rasterio/GDAL
into it can clash with QGIS's bundled GDAL. Instead the ScruTech plugin can point
at an *external* interpreter (e.g. the project's ``uv`` venv, which already has the
stack) and call:

    python -m vegevigie.qgis_runner <spec.json>

``spec.json`` holds the run parameters. Progress is streamed as ``PROGRESS <pct>
<msg>`` lines and the final output paths as a single ``RESULT <json>`` line, both
parsed by the plugin.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from vegevigie.pipeline import build_settings, run_pipeline


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("RESULT " + json.dumps({"error": "no spec file given"}))
        return 2

    spec = json.loads(Path(argv[0]).read_text())

    task = spec.get("task", "vegevigie_analyze")
    problem = area_problem(spec)
    if problem:
        print("RESULT " + json.dumps({"error": problem}), flush=True)
        return 1
    if task == "paf_interface_aoi":
        return _run_paf_interface_aoi(spec)
    if task == "alphaearth_change":
        return _run_alphaearth_change(spec)
    if task == "ecobuage_aoi":
        return _run_ecobuage_aoi(spec)
    if task == "biotrame_aoi":
        return _run_biotrame_aoi(spec)
    if task == "load_cached":
        return _run_load_cached(spec)
    if task == "geoai_segment":
        return _run_geoai_segment(spec)
    if task == "mnt_aoi":
        return _run_mnt_aoi(spec)
    if task == "ortho_aoi":
        return _run_ortho_aoi(spec)
    if task == "report":
        return _run_report(spec)

    zones = None
    if spec.get("zones_path"):
        import geopandas as gpd

        zones = gpd.read_file(spec["zones_path"])
    elif spec.get("auto_communes", True):
        # AOI-only: derive the communes to rank straight from the emprise (no layer needed).
        from core.aoi import communes_in_aoi

        try:
            zones = communes_in_aoi(tuple(spec["bbox"]))
            print(f"PROGRESS 10 Auto-derived {len(zones)} communes from the AOI.", flush=True)
        except Exception as exc:  # noqa: BLE001 — ranking is a bonus, don't fail the run
            print(f"PROGRESS 10 Commune auto-derivation skipped ({exc}).", flush=True)
        if zones is not None and zones.empty:
            zones = None

    settings = build_settings(
        tuple(spec["bbox"]),
        int(spec["start"]),
        int(spec["end"]),
        resolution=spec.get("resolution"),
        max_cloud_cover=spec.get("max_cloud"),
        data_dir=Path(spec["out_folder"]),
    )

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        result = run_pipeline(settings, zones=zones, progress=progress)
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    maps = (result.trend_tif, result.trend_class_tif, result.stress_tif, result.break_tif)
    _cache(spec, "vegevigie", [*maps, result.drought_tif, result.zonal_parquet])
    print(
        "RESULT "
        + json.dumps(
            {
                "trend_tif": _s(result.trend_tif),
                "trend_class_tif": _s(result.trend_class_tif),
                "stress_tif": _s(result.stress_tif),
                "break_tif": _s(result.break_tif),
                "drought_tif": _s(result.drought_tif),
                "zonal_parquet": _s(result.zonal_parquet),
                "timeline_parquet": _s(result.timeline_parquet),
                "scene_count": result.scene_count,
            }
        ),
        flush=True,
    )
    return 0


# Largest emprise (km²) before a run exhausts memory or takes hours; AlphaEarth samples and the
# DEM download are capped in their own code. ponytail: review estimates, calibrate on real runs.
_MAX_KM2 = {"paf_interface_aoi": 1000.0, "ecobuage_aoi": 1000.0}
_BIOTRAME_MAX_KM2 = {8: 5000.0, 9: 1000.0, 10: 150.0}
# VegeVigie costs pixels × months. Measured: 0.8 M pixel-months in 41 s, so 20 M is ~15 min.
_VEGEVIGIE_MAX_PIXEL_MONTHS = 20_000_000


def area_problem(spec: dict) -> str | None:
    """Why the emprise is too large for this task (plain French), or None if it is fine."""
    task = spec.get("task", "vegevigie_analyze")
    if "bbox" not in spec or task not in (*_MAX_KM2, "biotrame_aoi", "vegevigie_analyze"):
        return None
    from core.aoi import resolve_aoi

    km2 = resolve_aoi(tuple(spec["bbox"])).to_l93().area / 1e6
    advice = "Réduisez l'emprise (une commune ou un groupe de communes)"
    if task == "vegevigie_analyze":
        resolution = float(spec.get("resolution") or 60)
        months = 12 * (int(spec["end"]) - int(spec["start"]) + 1)
        limit = _VEGEVIGIE_MAX_PIXEL_MONTHS / months * resolution**2 / 1e6
        advice += ", prenez des pixels plus grands (résolution en m) ou raccourcissez la période"
    elif task == "biotrame_aoi":
        resolution = int(spec.get("resolution", 8))
        limit = _BIOTRAME_MAX_KM2.get(resolution, min(_BIOTRAME_MAX_KM2.values()))
    else:
        limit = _MAX_KM2[task]
    if km2 <= limit:
        return None

    def km(value: float) -> str:
        return f"{value:,.0f}".replace(",", "\u202f") + "\u00a0km²"

    return (
        f"Zone trop grande\u00a0: {km(km2)} pour {km(limit)} au plus avec ces réglages. {advice}."
    )


def _run_paf_interface_aoi(spec: dict) -> int:
    """AOI-only WUI: fetch forest+built-up from BD TOPO for the emprise, compute, write."""
    from vegevigie.interface import build_interface_from_aoi

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        line_path, zone_path, metrics = build_interface_from_aoi(
            tuple(spec["bbox"]),
            out_dir=Path(spec["out_folder"]),
            contact_m=float(spec.get("contact_m", 50.0)),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "paf", [line_path.with_suffix(".geojson"), zone_path.with_suffix(".geojson")])
    result = {"line_path": str(line_path), "zone_path": str(zone_path), **metrics}
    print("RESULT " + json.dumps(result), flush=True)
    return 0


def _run_alphaearth_change(spec: dict) -> int:
    """AOI-only AlphaEarth change: fetch the GEE cosine-change surface, flag, write."""
    from alphaearth.pipeline import detect_change_for_aoi
    from shapely.geometry import box, mapping

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        changed, geojson, summary = detect_change_for_aoi(
            mapping(box(*spec["bbox"])),
            int(spec["year1"]),
            int(spec["year2"]),
            out_dir=Path(spec["out_folder"]),
            percentile=float(spec.get("percentile", 95.0)),
            max_pixels=int(spec.get("max_pixels", 500_000)),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "alphaearth", [geojson])
    result = {"changed_path": str(changed), "geojson_path": str(geojson), **summary}
    print("RESULT " + json.dumps(result), flush=True)
    return 0


def _run_ecobuage_aoi(spec: dict) -> int:
    """AOI-only écobuage: slope (DEM) + access (roads) + exclusions (buildings) → aptitude."""
    from vegevigie.ecobuage_aoi import build_aptitude_from_aoi

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        apt_path, cls_path, info = build_aptitude_from_aoi(
            tuple(spec["bbox"]),
            spec.get("mnt_path"),
            out_dir=Path(spec["out_folder"]),
            resolution=float(spec.get("resolution", 25.0)),
            veg_trend_tif=spec.get("veg_trend_tif"),
            veg_drought_tif=spec.get("veg_drought_tif"),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "ecobuage", [apt_path, cls_path])
    result = {"aptitude_path": str(apt_path), "classes_path": str(cls_path), **info}
    print("RESULT " + json.dumps(result), flush=True)
    return 0


def _run_biotrame_aoi(spec: dict) -> int:
    """AOI-only biotrame: H3 mesh + reservoirs (+ optional trend degradation) → priority score."""
    from vegevigie.biotrame_aoi import build_priority_mesh_from_aoi

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        parquet, geojson, info = build_priority_mesh_from_aoi(
            tuple(spec["bbox"]),
            out_dir=Path(spec["out_folder"]),
            resolution=int(spec.get("resolution", 8)),
            veg_trend_tif=spec.get("veg_trend_tif"),
            mnt_path=spec.get("mnt_path"),
            corridor_max_m=float(spec.get("corridor_max_m", 2000.0)),
            tvb_wfs_url=spec.get("tvb_wfs_url"),
            tvb_typename=spec.get("tvb_typename"),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "biotrame", [geojson])
    result = {"parquet_path": str(parquet), "geojson_path": str(geojson), **info}
    print("RESULT " + json.dumps(result), flush=True)
    return 0


def _run_geoai_segment(spec: dict) -> int:
    """GeoAI: zero-shot segmentation of a raster with a locally-downloaded SAM checkpoint."""
    from vegevigie.geoai_segment import segment_raster

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        result = segment_raster(
            spec["raster_path"],
            out_dir=Path(spec["out_folder"]),
            points_per_side=int(spec.get("points_per_side", 32)),
            min_mask_region_area=int(spec.get("min_mask_region_area", 100)),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    payload = {
        "mask_path": str(result.mask_tif),
        "vector_path": str(result.vector_gpkg),
        "n_objects": result.n_objects,
    }
    print("RESULT " + json.dumps(payload), flush=True)
    return 0


def _run_mnt_aoi(spec: dict) -> int:
    """IGN DEM of the AOI (LiDAR HD, RGE ALTI in its gaps), tiled download then mosaic."""
    from core.sources import fetch_mnt

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        path, info = fetch_mnt(
            tuple(spec["bbox"]),
            Path(spec["out_path"]),
            resolution=float(spec.get("resolution", 5.0)),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1
    print("RESULT " + json.dumps({"mnt_path": str(path), **info}), flush=True)
    return 0


def _run_ortho_aoi(spec: dict) -> int:
    """IGN aerial photo of the AOI (BD ORTHO, RGB), tiled download then mosaic: SAM's input."""
    from core.sources import fetch_ortho

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        path, info = fetch_ortho(
            tuple(spec["bbox"]),
            Path(spec["out_path"]),
            resolution=float(spec.get("resolution", 0.5)),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1
    print("RESULT " + json.dumps({"ortho_path": str(path), **info}), flush=True)
    return 0


def _run_load_cached(spec: dict) -> int:
    """List the cached products for an AOI (no compute) so the plugin can load them."""
    from core.aoi import resolve_aoi
    from core.storage import data_root, list_cached

    try:
        aoi_id = resolve_aoi(tuple(spec["bbox"])).aoi_id
        paths = [str(p) for p in list_cached(aoi_id)]
    except Exception as exc:  # noqa: BLE001
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1
    payload = {"aoi_id": aoi_id, "paths": paths, "root": str(data_root())}
    print("RESULT " + json.dumps(payload), flush=True)
    return 0


def _run_report(spec: dict) -> int:
    """Write the HTML report of the AOI from its cached outputs, styled with the plugin's QML."""
    from core.aoi import resolve_aoi

    from vegevigie.report.html import build_report

    try:
        bbox = tuple(spec["bbox"])
        path, tools = build_report(
            resolve_aoi(bbox).aoi_id, bbox, spec.get("styles", {}), Path(spec["out_path"])
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1
    print("RESULT " + json.dumps({"html_path": str(path), "tools": tools}), flush=True)
    return 0


def _cache(spec: dict, pilier: str, files: list[Path | None]) -> None:
    """Copy a task's map products into the ScruTech store, keyed by aoi_id (for instant reload).

    Only the listed files: the output folder may hold intermediates (e.g. the downloaded DEM).
    """
    try:
        from core.aoi import resolve_aoi
        from core.storage import cache_outputs

        aoi_id = resolve_aoi(tuple(spec["bbox"])).aoi_id
        dests = cache_outputs(aoi_id, pilier, [f for f in files if f is not None])
        print(f"PROGRESS 99 Cached {len(dests)} product(s) under aoi={aoi_id}.", flush=True)
    except Exception as exc:  # noqa: BLE001 — caching is a bonus, never fail the run
        print(f"PROGRESS 99 Cache skipped ({exc}).", flush=True)


def _s(path: Path | None) -> str | None:
    return str(path) if path is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
