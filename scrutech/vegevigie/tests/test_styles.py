"""QML style generators produce well-formed XML (plugin _styles has no qgis deps)."""

from __future__ import annotations

import importlib.util
import xml.etree.ElementTree as ET
from pathlib import Path

_STYLES = (
    Path(__file__).resolve().parents[1] / "qgis_plugin" / "scrutech" / "algorithms" / "_styles.py"
)


def _load():
    # _styles.py vit dans qgis_plugin/ (un dossier qui n'est pas un package Python
    # importable normalement depuis les tests de vegevigie/). importlib.util permet
    # d'importer un module directement PAR SON CHEMIN DE FICHIER plutôt que par son nom
    # de package : spec_from_file_location décrit le module à charger,
    # module_from_spec crée l'objet module vide, exec_module l'exécute pour le remplir
    # — l'équivalent bas niveau de ce que fait `import` normalement en coulisses.
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
        "trend_class_qml",
        "stress_frequency_qml",
        "paff_line_qml",
        "paff_zone_qml",
    ):
        xml = getattr(m, name)()
        body = xml.split(">\n", 1)[1]  # drop the DOCTYPE line for the parser
        # ET.fromstring parse le texte XML et lève une exception s'il est mal formé
        # (balise non fermée, etc.) : on ne vérifie pas ICI que le contenu est correct
        # pour QGIS, juste que le XML généré est syntaxiquement valide.
        ET.fromstring(body)  # raises if malformed


def test_biotrame_qml_categorizes_on_classe() -> None:
    m = _load()
    xml = m.biotrame_qml()
    assert 'attr="classe"' in xml
    assert xml.count("<category ") == 3  # 3 classes


def test_vegevigie_styles_are_readable_classes() -> None:
    m = _load()
    # Discrete classes with a plain-French legend, not a continuous grey ramp.
    for xml in (m.trend_qml(), m.drought_qml(), m.stress_frequency_qml()):
        assert 'colorRampType="DISCRETE"' in xml and 'value="inf"' in xml
    assert "en dessous de la normale" in m.drought_qml()
    # One colour per year, light for early breaks and dark for recent ones.
    years = m.break_year_qml(2020, 2025)
    ET.fromstring(years.split(">\n", 1)[1])
    assert years.count("<paletteEntry ") == 6 and "rupture en 2025" in years
    assert m._blend("#000000", "#ffffff", 0.5) == "#808080"


def test_style_for_matches_output_names() -> None:
    m = _load()
    assert m.style_for(r"C:\cache\trend_sen_slope_2021_2024.tif") == m.trend_qml()
    assert "rupture en 2023" in m.style_for("/cache/break_year_2021_2024.tif")
    assert m.style_for("mnt_ign.tif") is None
    assert set(m.report_styles()) >= {"trend_sen_slope_", "ecobuage_classes", "biotrame_priority"}
