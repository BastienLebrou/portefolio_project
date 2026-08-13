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
    if task == "paf_interface_aoi":
        return _run_paf_interface_aoi(spec)
    if task == "alphaearth_change":
        return _run_alphaearth_change(spec)
    if task == "ecobuage_aoi":
        return _run_ecobuage_aoi(spec)

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

    print(
        "RESULT "
        + json.dumps(
            {
                "trend_tif": _s(result.trend_tif),
                "drought_tif": _s(result.drought_tif),
                "zonal_parquet": _s(result.zonal_parquet),
                "timeline_parquet": _s(result.timeline_parquet),
                "scene_count": result.scene_count,
            }
        ),
        flush=True,
    )
    return 0


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
            spec["mnt_path"],
            out_dir=Path(spec["out_folder"]),
            resolution=float(spec.get("resolution", 25.0)),
            veg_trend_tif=spec.get("veg_trend_tif"),
            veg_drought_tif=spec.get("veg_drought_tif"),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    result = {"aptitude_path": str(apt_path), "classes_path": str(cls_path), **info}
    print("RESULT " + json.dumps(result), flush=True)
    return 0


def _s(path: Path | None) -> str | None:
    return str(path) if path is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
