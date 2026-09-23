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
    if task == "projection":
        return _run_projection(spec)
    if task == "diagnostic":
        return _run_diagnostic(spec)

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


def _run_diagnostic(spec: dict) -> int:
    """Every emprise analysis in a row, then the HTML report: the one-click diagnostic.

    Engine-side so both front ends (the ScruTech desktop app and the QGIS plugin) share one
    sequence. A failing step is skipped with its reason, never fatal: a missing GEE key must
    not cost the rest.
    """
    from core.aoi import resolve_aoi
    from core.storage import data_root

    bbox = tuple(spec["bbox"])
    root = Path(spec["out_folder"])
    start, end = int(spec.get("start", 2020)), int(spec.get("end", 2025))
    pixel = int(spec.get("resolution", 30))
    hexagons = int(spec.get("hexagons", 8))
    aoi_id = resolve_aoi(bbox).aoi_id
    state: dict = {}
    done: list[str] = []
    skipped: dict[str, str] = {}

    steps = [
        ("MNT IGN de la zone", lambda: _step_mnt(bbox, root, pixel, state)),
        (
            "Végétation (VegeVigie)",
            lambda: _step_vegevigie(spec, bbox, root, start, end, pixel, state),
        ),
        ("Changements (AlphaEarth)", lambda: _step_alphaearth(spec, bbox, root, start, end)),
        ("Interface habitat-forêt (PAFF)", lambda: _step_paff(spec, bbox, root)),
        ("Aptitude à l'écobuage", lambda: _step_ecobuage(spec, bbox, root, pixel, state)),
        (
            "Priorisation écologique (Biotrame)",
            lambda: _step_biotrame(spec, bbox, root, hexagons, state),
        ),
        ("Projection climatique", lambda: _step_projection(spec, bbox, root, state)),
    ]
    for i, (label, run) in enumerate(steps):
        print(f"PROGRESS {5 + int(85 * i / len(steps))} {label}…", flush=True)
        try:
            run()
            done.append(label)
        except Exception as exc:  # noqa: BLE001 — one failing step must not cost the rest
            skipped[label] = str(exc).strip().splitlines()[0][:300]
            print(f"{label} : étape sautée. {skipped[label]}", flush=True)

    report_path = None
    if done:
        print("PROGRESS 92 Rapport de synthèse…", flush=True)
        try:
            from vegevigie.report.html import build_report

            report_path, _tools = build_report(aoi_id, bbox, None, root / "rapport_diagnostic.html")
        except Exception as exc:  # noqa: BLE001 — the layers are there even without the page
            skipped["Rapport de synthèse"] = str(exc).strip()[:300]
    result = {
        "aoi_id": aoi_id,
        "done": done,
        "skipped": skipped,
        "report_path": str(report_path) if report_path else None,
        "paths": [str(p) for p in sorted(_cached_paths(aoi_id))],
        "data_root": str(data_root()),
    }
    print(f"PROGRESS 100 Diagnostic : {len(done)} étape(s) sur {len(steps)}.", flush=True)
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0


def _cached_paths(aoi_id: str) -> list[Path]:
    from core.storage import list_cached

    return list_cached(aoi_id)


def _step_mnt(bbox: tuple, root: Path, pixel: int, state: dict) -> None:
    """The IGN DEM at 5 m when the zone allows it, else at the analysis pixel."""
    from core.aoi import resolve_aoi
    from core.sources import MNT_MAX_PX, fetch_mnt

    minx, miny, maxx, maxy = resolve_aoi(bbox).to_l93().bounds
    fits_5m = (maxx - minx) * (maxy - miny) / 25.0 <= MNT_MAX_PX
    path, _info = fetch_mnt(
        bbox,
        root / "mnt" / "mnt.tif",
        resolution=5.0 if fits_5m else float(pixel),
        progress=_progress,
    )
    state["mnt"] = path


def _step_vegevigie(spec, bbox, root, start, end, pixel, state) -> None:
    from vegevigie.pipeline import build_settings, run_pipeline

    zones = None
    try:
        from core.aoi import communes_in_aoi

        zones = communes_in_aoi(bbox)
        zones = None if zones.empty else zones
    except Exception:  # noqa: BLE001 — ranking is a bonus
        zones = None
    settings = build_settings(
        bbox,
        start,
        end,
        resolution=pixel,
        max_cloud_cover=spec.get("max_cloud"),
        data_dir=root / "vegevigie",
    )
    result = run_pipeline(settings, zones=zones, progress=_progress)
    maps = (result.trend_tif, result.trend_class_tif, result.stress_tif, result.break_tif)
    _cache(spec, "vegevigie", [*maps, result.drought_tif, result.zonal_parquet])
    state.update(
        trend=result.trend_tif,
        trend_class=result.trend_class_tif,
        drought=result.drought_tif,
        stress=result.stress_tif,
    )


def _step_alphaearth(spec, bbox, root, start, end) -> None:
    import os

    from alphaearth.pipeline import detect_change_for_aoi
    from shapely.geometry import box, mapping

    # The key as the front ends pass it, else the one saved in the user's folder.
    key_file = Path.home() / ".scrutech" / "gee_key.json"
    credentials = os.environ.get("SCRUTECH_GEE_CREDENTIALS") or (
        key_file.read_text(encoding="utf-8") if key_file.is_file() else None
    )
    if credentials is None:
        raise RuntimeError(
            "Pas de clé Google Earth Engine : rangez-la dans ~/.scrutech/gee_key.json "
            "(onglet Configuration) pour activer AlphaEarth."
        )
    _changed, geojson, _summary = detect_change_for_aoi(
        mapping(box(*bbox)),
        start,
        end,
        out_dir=root / "alphaearth",
        credentials_json=credentials,
        progress=_progress,
    )
    _cache(spec, "alphaearth", [geojson])


def _step_paff(spec, bbox, root) -> None:
    from vegevigie.interface import build_interface_from_aoi

    line, zone, _metrics = build_interface_from_aoi(
        bbox, out_dir=root / "paff", contact_m=50.0, progress=_progress
    )
    _cache(spec, "paf", [line.with_suffix(".geojson"), zone.with_suffix(".geojson")])


def _step_ecobuage(spec, bbox, root, pixel, state) -> None:
    from vegevigie.ecobuage_aoi import build_aptitude_from_aoi

    aptitude, classes, _info = build_aptitude_from_aoi(
        bbox,
        state.get("mnt"),
        out_dir=root / "ecobuage",
        resolution=pixel,
        veg_trend_tif=state.get("trend"),
        veg_drought_tif=state.get("drought"),
        progress=_progress,
    )
    _cache(spec, "ecobuage", [aptitude, classes])


def _step_biotrame(spec, bbox, root, hexagons, state) -> None:
    from vegevigie.biotrame_aoi import build_priority_mesh_from_aoi

    _parquet, geojson, _info = build_priority_mesh_from_aoi(
        bbox,
        out_dir=root / "biotrame",
        resolution=hexagons,
        veg_trend_tif=state.get("trend"),
        mnt_path=state.get("mnt"),
        progress=_progress,
    )
    _cache(spec, "biotrame", [geojson])


def _step_projection(spec, bbox, root, state) -> None:
    from core.storage import data_root

    from vegevigie.projection import build_projection

    minx, miny, maxx, maxy = bbox
    files, _summary = build_projection(
        (miny + maxy) / 2,
        (minx + maxx) / 2,
        root / "projection",
        stress_tif=state.get("stress"),
        trend_tif=state.get("trend"),
        trend_class_tif=state.get("trend_class"),
        cache_dir=data_root() / "climat",
        progress=_progress,
    )
    _cache(spec, "projection", list(files))


def _progress(pct: int, msg: str) -> None:
    print(f"PROGRESS {pct} {msg}", flush=True)


def _run_projection(spec: dict) -> int:
    """Future climate of the zone (+10 to +30 years) and exposure maps from its cached state."""
    from core.aoi import resolve_aoi
    from core.storage import data_root

    from vegevigie.projection import build_projection
    from vegevigie.report.data import discover

    def progress(pct: int, msg: str) -> None:
        print(f"PROGRESS {pct} {msg}", flush=True)

    try:
        minx, miny, maxx, maxy = spec["bbox"]
        # The zone's vegetation today, as last analysed (VegeVigie); climate only if none.
        today = discover(data_root(), resolve_aoi(tuple(spec["bbox"])).aoi_id)
        if today.stress is None and today.trend is None:
            progress(5, "Pas d'analyse VegeVigie de la zone : climat seul, sans carte.")
        files, summary = build_projection(
            (miny + maxy) / 2,
            (minx + maxx) / 2,
            Path(spec["out_folder"]),
            stress_tif=today.stress,
            trend_tif=today.trend,
            trend_class_tif=today.trend_class,
            cache_dir=data_root() / "climat",
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc)}), flush=True)
        return 1

    _cache(spec, "projection", list(files))
    result = {"paths": [str(f) for f in files], **summary}
    print("RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
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
