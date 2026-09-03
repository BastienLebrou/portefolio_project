"""ScruTech QML styles for the VegeVigie rasters — automatic, readable output.

Environmental cartography semiology: a **diverging brown→green** ramp for the greening/
browning trend (the established convention — greenbrown / RdYlGn), and a diverging
drought ramp (dry brown/red → wet green). Never a rainbow ramp (false boundaries,
unreadable for colour-blind users).

Refs: greenbrown brgr.colors (brown-to-green NDVI trend palette); ColorBrewer RdYlGn.
"""

from __future__ import annotations

# (value, hex, label)
_TREND_STOPS = [
    (-0.02, "#8c510a", "brunissement"),
    (-0.005, "#d8b365", ""),
    (0.0, "#f5f5f5", "stable"),
    (0.005, "#7fbf7b", ""),
    (0.02, "#1a9850", "verdissement"),
]
_DROUGHT_STOPS = [
    (-2.0, "#d73027", "sécheresse forte"),
    (-1.0, "#fc8d59", ""),
    (0.0, "#ffffbf", "normale"),
    (1.0, "#91cf60", ""),
    (2.0, "#1a9850", "humide"),
]


# Un fichier .qml est le format natif de QGIS pour décrire le STYLE d'une couche (ici,
# quelle couleur donner à quelle valeur de pixel) : simplement du XML. QGIS charge
# automatiquement un .qml portant le même nom qu'une couche à côté d'elle. En générant
# ce texte nous-mêmes plutôt qu'en configurant le style à la main dans QGIS, chaque
# résultat s'affiche déjà correctement stylé dès son premier chargement.
def _qml(band: int, cmin: float, cmax: float, stops: list[tuple[float, str, str]]) -> str:
    items = "\n".join(
        f'          <item value="{v}" label="{lbl}" color="{c}" alpha="255"/>'
        for v, c, lbl in stops
    )
    return (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.34" styleCategories="AllStyleCategories">\n'
        "  <pipe>\n"
        f'    <rasterrenderer type="singlebandpseudocolor" band="{band}" opacity="1"'
        f' classificationMin="{cmin}" classificationMax="{cmax}">\n'
        "      <rastershader>\n"
        '        <colorrampshader colorRampType="INTERPOLATED" clip="0">\n'
        f"{items}\n"
        "        </colorrampshader>\n"
        "      </rastershader>\n"
        "    </rasterrenderer>\n"
        "  </pipe>\n"
        "</qgis>\n"
    )


def trend_qml() -> str:
    """Sen's slope (NDVI/month): brown = browning, green = greening (centred on 0)."""
    return _qml(1, -0.02, 0.02, _TREND_STOPS)


def drought_qml() -> str:
    """NDVI anomaly (z-score): red/brown = drought, green = wet (centred on 0)."""
    return _qml(1, -2.0, 2.0, _DROUGHT_STOPS)


# Aptitude 0-100 ramp (écobuage): grey (unsuitable) → green (suitable to burn).
_APTITUDE_STOPS = [
    (0.0, "#cccccc", "nulle"),
    (33.0, "#fdae61", "faible"),
    (66.0, "#a6d96a", "modérée"),
    (100.0, "#1a9850", "forte"),
]


def ecobuage_aptitude_qml() -> str:
    """Écobuage aptitude (0-100): grey = unsuitable, green = suitable."""
    return _qml(1, 0.0, 100.0, _APTITUDE_STOPS)


def _paletted_qml(entries: list[tuple[int, str, str]]) -> str:
    """A paletted (categorical) raster QML for small integer class rasters."""
    items = "\n".join(
        f'        <paletteEntry value="{v}" color="{c}" label="{lbl}" alpha="255"/>'
        for v, c, lbl in entries
    )
    return (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.34" styleCategories="AllStyleCategories">\n'
        "  <pipe>\n"
        '    <rasterrenderer type="paletted" band="1" opacity="1">\n'
        "      <colorPalette>\n"
        f"{items}\n"
        "      </colorPalette>\n"
        "    </rasterrenderer>\n"
        "  </pipe>\n"
        "</qgis>\n"
    )


def ecobuage_classes_qml() -> str:
    """Écobuage 3-class raster: 0 exclure (grey) / 1 à étudier (orange) / 2 prioritaire (green)."""
    return _paletted_qml(
        [(0, "#cccccc", "à exclure"), (1, "#fdae61", "à étudier"), (2, "#1a9850", "prioritaire")]
    )


# Biotrame classes (vector): alert semiology — the more urgent, the redder.
_BIOTRAME_CATEGORIES = [
    (2, "215,48,39,255", "prioritaire"),
    (1, "253,174,97,255", "à étudier"),
    (0, "204,204,204,255", "secondaire"),
]


def _fill_symbol(name: str, rgba: str) -> str:
    return (
        f'      <symbol name="{name}" type="fill" alpha="0.7">\n'
        '        <layer class="SimpleFill">\n'
        '          <Option type="Map">\n'
        f'            <Option name="color" type="QString" value="{rgba}"/>\n'
        '            <Option name="outline_color" type="QString" value="90,90,90,255"/>\n'
        '            <Option name="outline_width" type="QString" value="0.1"/>\n'
        '            <Option name="style" type="QString" value="solid"/>\n'
        "          </Option>\n"
        "        </layer>\n"
        "      </symbol>"
    )


def biotrame_qml() -> str:
    """Vector categorized style on the ``classe`` field (0/1/2), alert palette."""
    cats = "\n".join(
        f'      <category value="{v}" symbol="{i}" label="{lbl}" render="true"/>'
        for i, (v, _rgba, lbl) in enumerate(_BIOTRAME_CATEGORIES)
    )
    syms = "\n".join(
        _fill_symbol(str(i), rgba) for i, (_v, rgba, _lbl) in enumerate(_BIOTRAME_CATEGORIES)
    )
    return (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.34" styleCategories="Symbology">\n'
        '  <renderer-v2 type="categorizedSymbol" attr="classe" forceraster="0"'
        ' symbollevels="0" enableorderby="0">\n'
        "    <categories>\n"
        f"{cats}\n"
        "    </categories>\n"
        "    <symbols>\n"
        f"{syms}\n"
        "    </symbols>\n"
        "  </renderer-v2>\n"
        "</qgis>\n"
    )
