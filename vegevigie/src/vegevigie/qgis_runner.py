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
    zones = None
    if spec.get("zones_path"):
        import geopandas as gpd

        zones = gpd.read_file(spec["zones_path"])

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


def _s(path: Path | None) -> str | None:
    return str(path) if path is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
