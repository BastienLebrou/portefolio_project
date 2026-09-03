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
