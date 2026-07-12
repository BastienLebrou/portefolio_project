"""Subprocess entry point so the QGIS plugin can run the engine out-of-process.

QGIS ships its own Python without the datacube stack, and installing rasterio/GDAL
into it can clash with QGIS's bundled GDAL. Instead the ScruTech plugin points at
an *external* interpreter (e.g. the project's ``uv`` venv, which already has the
stack) and calls:

    python -m vegevigie.qgis_runner <spec.json>

``spec.json`` holds the run parameters. Since the S1 spine refactor the spec may
also name a **single stage** (``"stage": "search" | "composites" | "trend" |
"drought" | "zonal" | "rank"``; default ``"all"`` = full pipeline), which is how
every ScruTech per-stage algorithm shares this one subprocess entry point.

Line protocol (parsed by the plugin, see ``qgis_plugin/scrutech/protocol.py``):

- ``PROGRESS <pct> <msg>`` — progress updates;
- ``HEARTBEAT`` — emitted every few seconds so the plugin's blocking reader wakes
  up and can honour a cancel request even while the engine is silent;
- ``RESULT <json>`` — one final line with the output paths (or an ``error`` key).
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

STAGE_ALL = "all"
DEFAULT_HEARTBEAT_SECONDS = 10.0


def _progress(pct: int, msg: str) -> None:
    print(f"PROGRESS {pct} {msg}", flush=True)


class _Heartbeat:
    """Print ``HEARTBEAT`` periodically so the parent can poll cancellation."""

    def __init__(self, interval: float = DEFAULT_HEARTBEAT_SECONDS) -> None:
        self._interval = max(0.01, float(interval))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            print("HEARTBEAT", flush=True)

    def __enter__(self) -> _Heartbeat:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()


def settings_for_spec(spec: dict[str, Any]) -> Any:
    """Build Settings from the spec (entry stages) or the run-folder manifest."""
    from vegevigie.pipeline import build_settings
    from vegevigie.stages import STAGE_SEARCH, load_manifest_settings

    out_folder = Path(spec["out_folder"])
    stage = spec.get("stage", STAGE_ALL)
    if stage in (STAGE_ALL, STAGE_SEARCH) and spec.get("bbox"):
        return build_settings(
            tuple(spec["bbox"]),
            int(spec["start"]),
            int(spec["end"]),
            resolution=spec.get("resolution"),
            max_cloud_cover=spec.get("max_cloud"),
            data_dir=out_folder,
        )
    # Downstream stages re-anchor on the manifest written by the entry stage.
    return load_manifest_settings(out_folder)


def _load_zones(spec: dict[str, Any]) -> Any:
    if not spec.get("zones_path"):
        return None
    import geopandas as gpd

    return gpd.read_file(spec["zones_path"])


def run_all_payload(
    spec: dict[str, Any], settings: Any, progress: Any = _progress
) -> dict[str, Any]:
    """Run the full pipeline for ``spec`` and shape the result payload.

    Public because the ScruTech base algorithm reuses it for in-process runs, so
    both execution modes hand the plugin the exact same payload shape.
    """
    from vegevigie.pipeline import run_pipeline

    result = run_pipeline(
        settings,
        zones=_load_zones(spec),
        force=bool(spec.get("force")),
        progress=progress,
    )
    return {
        "stage": STAGE_ALL,
        "scene_count": result.scene_count,
        "trend_tif": _s(result.trend_tif),
        "trend_class_tif": _s(result.trend_class_tif),
        "pvalue_tif": _s(result.pvalue_tif),
        "drought_tif": _s(result.drought_tif),
        "vci_tif": _s(result.vci_tif),
        "zonal_parquet": _s(result.zonal_parquet),
        "zonal_gpkg": _s(result.zonal_gpkg),
        "duckdb": _s(result.duckdb_path),
        "timeline_parquet": _s(result.timeline_parquet),
    }


def run_stage_payload(
    spec: dict[str, Any], settings: Any, stage: str, progress: Any = _progress
) -> dict[str, Any]:
    """Run one stage for ``spec`` and shape the result payload (see run_all_payload)."""
    from vegevigie.stages import run_stage

    outcome = run_stage(
        stage,
        settings,
        zones=_load_zones(spec),
        force=bool(spec.get("force")),
        progress=progress,
        metric=spec.get("metric", "mean_sen_slope"),
        ascending=bool(spec.get("ascending", False)),
        limit=int(spec.get("limit", 10)),
    )
    return {
        "stage": outcome.stage,
        "skipped": outcome.skipped,
        "artifacts": {key: str(p) for key, p in outcome.artifacts.items()},
        "meta": outcome.meta,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("RESULT " + json.dumps({"error": "no spec file given"}))
        return 2

    spec = json.loads(Path(argv[0]).read_text())
    stage = spec.get("stage", STAGE_ALL)
    heartbeat = float(spec.get("heartbeat", DEFAULT_HEARTBEAT_SECONDS))
    try:
        settings = settings_for_spec(spec)
        with _Heartbeat(heartbeat):
            payload = (
                run_all_payload(spec, settings)
                if stage == STAGE_ALL
                else run_stage_payload(spec, settings, stage)
            )
    except Exception as exc:  # noqa: BLE001 — report to the plugin, don't traceback-crash
        print("RESULT " + json.dumps({"error": str(exc), "stage": stage}), flush=True)
        return 1

    print("RESULT " + json.dumps(payload), flush=True)
    return 0


def _s(path: Path | None) -> str | None:
    return str(path) if path is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
