"""Subprocess entry point so the QGIS plugin can run the pipeline out-of-process.

QGIS ships its own Python without the datacube stack, and installing rasterio/GDAL
into it can clash with QGIS's bundled GDAL. Instead the ScruTech plugin can point
at an *external* interpreter (e.g. the project's ``uv`` venv, which already has the
stack) and call:

    python -m vegevigie.qgis_runner <spec.json>

``spec.json`` holds the run parameters. Progress is streamed as ``PROGRESS <pct>
<msg>`` lines and the final output paths as a single ``RESULT <json>`` line, both
parsed by the plugin.

MÉCANISME DE COMMUNICATION ENTRE PROCESSUS : QGIS (processus A) lance ce script comme un
sous-processus (processus B, avec un AUTRE interpréteur Python) et lit sa sortie standard
(stdout) ligne par ligne pendant qu'il tourne. Comme les deux processus ne partagent pas
de mémoire, on ne peut pas juste "retourner" un objet Python : on communique par du TEXTE
simple sur un flux — chaque `print("PROGRESS ...")` est immédiatement lu côté QGIS pour
mettre à jour sa barre de progression, et la ligne finale `print("RESULT ...")` porte le
résultat encodé en JSON (un format texte universel, lisible par n'importe quel langage).
`flush=True` force l'envoi immédiat de chaque ligne : sans lui, Python mettrait en mémoire
tampon sa sortie, et QGIS ne recevrait les messages que par paquets, en retard.
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
    if task == "biotrame_aoi":
        return _run_biotrame_aoi(spec)
    if task == "load_cached":
        return _run_load_cached(spec)

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

    _cache(spec, "paf")
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

    _cache(spec, "alphaearth")
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

    _cache(spec, "ecobuage")
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
            corridor_max_m=float(spec.get("corridor_max_m", 2000.0)),
            tvb_wfs_url=spec.get("tvb_wfs_url"),
            tvb_typename=spec.get("tvb_typename"),
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "biotrame")
    result = {"parquet_path": str(parquet), "geojson_path": str(geojson), **info}
    print("RESULT " + json.dumps(result), flush=True)
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


def _cache(spec: dict, pilier: str) -> None:
    """Copy an AOI task's outputs into the ScruTech store, keyed by aoi_id (for instant reload)."""
    try:
        from core.aoi import resolve_aoi
        from core.storage import _LOADABLE, cache_outputs

        folder = Path(spec["out_folder"])
        files = [p for p in folder.glob("*") if p.suffix.lower() in _LOADABLE]
        aoi_id = resolve_aoi(tuple(spec["bbox"])).aoi_id
        dests = cache_outputs(aoi_id, pilier, files)
        print(f"PROGRESS 99 Cached {len(dests)} product(s) under aoi={aoi_id}.", flush=True)
    except Exception as exc:  # noqa: BLE001 — caching is a bonus, never fail the run
        print(f"PROGRESS 99 Cache skipped ({exc}).", flush=True)


def _s(path: Path | None) -> str | None:
    return str(path) if path is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
