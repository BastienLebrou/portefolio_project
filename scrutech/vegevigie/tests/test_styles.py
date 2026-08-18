"""QML style generators produce well-formed XML (plugin _styles has no qgis deps)."""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

_STYLES = (
    Path(__file__).resolve().parents[1] / "qgis_plugin" / "scrutech" / "algorithms" / "_styles.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_scrutech_styles", _STYLES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_qml_are_wellformed_xml() -> None:
    m = _load()
    for name in (
        "trend_qml",
        "drought_qml",
        "ecobuage_aptitude_qml",
        "ecobuage_classes_qml",
        "biotrame_qml",
    ):
        xml = getattr(m, name)()
        body = xml.split(">\n", 1)[1]  # drop the DOCTYPE line for the parser
        ET.fromstring(body)  # raises if malformed


def test_biotrame_qml_categorizes_on_classe() -> None:
    m = _load()
    xml = m.biotrame_qml()
    assert 'attr="classe"' in xml
    assert xml.count("<category ") == 3  # 3 classes
