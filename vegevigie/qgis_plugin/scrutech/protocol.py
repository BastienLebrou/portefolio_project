"""Spec building + line-protocol parsing shared by every ScruTech algorithm.

Pure Python — **no qgis imports** — so this module is unit-tested in CI without
a QGIS runtime (see ``tests/test_scrutech_protocol.py``). The contract mirrors
``vegevigie.qgis_runner``: the plugin writes a JSON *spec* describing one engine
stage, and parses the runner's stdout lines:

- ``PROGRESS <pct> <msg>`` — progress updates;
- ``HEARTBEAT`` — keep-alive so the reader can poll cancellation;
- ``RESULT <json>`` — final payload (output paths, or an ``error`` key);
- anything else — plain log text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Stage names — must match vegevigie.stages (pinned by a test).
STAGE_ALL = "all"
STAGE_SEARCH = "search"
STAGE_COMPOSITES = "composites"
STAGE_TREND = "trend"
STAGE_DROUGHT = "drought"
STAGE_ZONAL = "zonal"
STAGE_RANK = "rank"

PROGRESS_PREFIX = "PROGRESS "
RESULT_PREFIX = "RESULT "
HEARTBEAT = "HEARTBEAT"


def build_spec(
    stage: str,
    out_folder: str,
    *,
    bbox: tuple[float, float, float, float] | list[float] | None = None,
    start: int | None = None,
    end: int | None = None,
    resolution: int | None = None,
    max_cloud: float | None = None,
    zones_path: str | None = None,
    force: bool = False,
    metric: str | None = None,
    ascending: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Assemble the run spec consumed by ``python -m vegevigie.qgis_runner``.

    Entry stages (``all``/``search``) carry the AOI + window; downstream stages
    only need the run folder — their settings come from its manifest.
    """
    spec: dict[str, Any] = {"stage": stage, "out_folder": out_folder, "force": bool(force)}
    if bbox is not None:
        spec["bbox"] = [float(c) for c in bbox]
    if start is not None:
        spec["start"] = int(start)
    if end is not None:
        spec["end"] = int(end)
    if resolution is not None:
        spec["resolution"] = int(resolution)
    if max_cloud is not None:
        spec["max_cloud"] = float(max_cloud)
    if zones_path is not None:
        spec["zones_path"] = zones_path
    if metric is not None:
        spec["metric"] = metric
    if ascending is not None:
        spec["ascending"] = bool(ascending)
    if limit is not None:
        spec["limit"] = int(limit)
    return spec


@dataclass
class ParsedLine:
    """One decoded stdout line from the runner."""

    kind: str  # "progress" | "result" | "heartbeat" | "log"
    percent: int | None = None
    message: str = ""
    payload: dict[str, Any] | None = None


def parse_line(raw: str) -> ParsedLine:
    """Decode one runner stdout line; anything unrecognized comes back as a log."""
    line = raw.rstrip("\r\n")
    if line == HEARTBEAT:
        return ParsedLine("heartbeat")
    if line.startswith(PROGRESS_PREFIX):
        pct_str, _, message = line[len(PROGRESS_PREFIX) :].partition(" ")
        try:
            percent = int(pct_str)
        except ValueError:
            return ParsedLine("log", message=line)
        return ParsedLine("progress", percent=percent, message=message)
    if line.startswith(RESULT_PREFIX):
        try:
            payload = json.loads(line[len(RESULT_PREFIX) :])
        except ValueError:
            return ParsedLine("log", message=line)
        return ParsedLine("result", payload=payload)
    return ParsedLine("log", message=line)


def explain_error(text: str) -> str:
    """Turn a raw engine error into an actionable message for the QGIS log."""
    if any(marker in text for marker in ("403", "Forbidden", "Proxy", "Max retries")):
        return (
            "Could not reach Microsoft Planetary Computer "
            "(planetarycomputer.microsoft.com). Check internet access / proxy / "
            "firewall and retry.\n\nOriginal error: " + text
        )
    return "Pipeline failed: " + text
