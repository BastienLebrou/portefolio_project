"""ScruTech protocol tests — the plugin <-> runner contract, without QGIS (§8).

``qgis_plugin/scrutech/protocol.py`` is deliberately qgis-free so the wire
format the plugin parses can be pinned in CI. Loaded from its file path because
importing the ``scrutech`` package would pull in the QGIS API.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

PROTOCOL_PATH = Path(__file__).resolve().parents[1] / "qgis_plugin" / "scrutech" / "protocol.py"


def _load_protocol() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scrutech_protocol", PROTOCOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the owning module through sys.modules at class-creation
    # time, so the module must be registered before exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load_protocol()


def test_stage_names_match_engine() -> None:
    """The plugin's stage vocabulary must stay in lockstep with the engine's."""
    from vegevigie import qgis_runner, stages

    assert protocol.STAGE_ALL == qgis_runner.STAGE_ALL
    assert protocol.STAGE_SEARCH == stages.STAGE_SEARCH
    assert protocol.STAGE_COMPOSITES == stages.STAGE_COMPOSITES
    assert protocol.STAGE_TREND == stages.STAGE_TREND
    assert protocol.STAGE_DROUGHT == stages.STAGE_DROUGHT
    assert protocol.STAGE_ZONAL == stages.STAGE_ZONAL
    assert protocol.STAGE_RANK == stages.STAGE_RANK


def test_parse_progress_line() -> None:
    line = protocol.parse_line("PROGRESS 42 Building datacube from 12 scenes…\n")
    assert (line.kind, line.percent) == ("progress", 42)
    assert line.message == "Building datacube from 12 scenes…"


def test_parse_result_line() -> None:
    line = protocol.parse_line('RESULT {"stage": "trend", "artifacts": {"sen_slope": "t.tif"}}')
    assert line.kind == "result"
    assert line.payload == {"stage": "trend", "artifacts": {"sen_slope": "t.tif"}}


def test_parse_heartbeat_and_log() -> None:
    assert protocol.parse_line("HEARTBEAT\n").kind == "heartbeat"
    log = protocol.parse_line("some engine chatter")
    assert (log.kind, log.message) == ("log", "some engine chatter")


def test_malformed_lines_fall_back_to_log() -> None:
    assert protocol.parse_line("PROGRESS notanumber msg").kind == "log"
    assert protocol.parse_line("RESULT {not json").kind == "log"


def test_build_spec_entry_stage() -> None:
    spec = protocol.build_spec(
        protocol.STAGE_SEARCH,
        "/runs/demo",
        bbox=(4.5, 44.5, 4.7, 44.6),
        start=2019,
        end=2022,
        resolution=60,
        max_cloud=50,
        force=True,
    )
    assert spec["stage"] == "search"
    assert spec["bbox"] == [4.5, 44.5, 4.7, 44.6]
    assert (spec["start"], spec["end"]) == (2019, 2022)
    assert spec["force"] is True
    assert "zones_path" not in spec  # optional fields stay absent, not None


def test_build_spec_downstream_stage_is_minimal() -> None:
    spec = protocol.build_spec(protocol.STAGE_TREND, "/runs/demo")
    assert spec == {"stage": "trend", "out_folder": "/runs/demo", "force": False}


def test_explain_error_flags_network_issues() -> None:
    assert "Planetary Computer" in protocol.explain_error("403 Forbidden from proxy")
    assert protocol.explain_error("boom").startswith("Pipeline failed: boom")
