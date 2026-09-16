"""ScruTech QML styles: every colour says one plain-French thing.

Environmental cartography semiology: diverging brown→green for greening/browning, diverging
red→green for the deviation from normal, sequential ramps for frequencies and years, never a
rainbow (false boundaries, unreadable for colour-blind users). Classes are DISCRETE so the
legend reads as sentences ("net dépérissement", "en dessous de la normale"…) rather than raw
numbers. Pure strings, no QGIS import (unit-tested offline).

Refs: greenbrown brgr.colors (NDVI trend palette); ColorBrewer BrBG / RdYlGn / OrRd.
"""

from __future__ import annotations

# DISCRETE classes: (upper bound, colour, legend); a class holds the values up to its bound.
# Sen slope of the deseasonalized monthly NDVI, in NDVI units per month.
_TREND_CLASSES = [
    (-0.003, "#8c510a", "net dépérissement"),
    (-0.001, "#d8b365", "léger dépérissement"),
    (0.001, "#f5f5f5", "stable"),
    (0.003, "#7fbf7b", "léger verdissement"),
    ("inf", "#1b7837", "net verdissement"),
]
# NDVI anomaly of the last year, mean of its monthly z-scores (a yearly mean is much
# narrower than a monthly z: ±1 would paint almost everything 'normal').
_DROUGHT_CLASSES = [
    (-0.75, "#b2182b", "très en dessous de la normale"),
    (-0.25, "#ef8a62", "en dessous de la normale"),
    (0.25, "#f7f7f7", "proche de la normale"),
    (0.75, "#a6dba0", "au-dessus de la normale"),
    ("inf", "#1b7837", "très au-dessus de la normale"),
]
# Share of observed months under stress (anomaly <= -1), in %; ~16 % is statistically
# expected, so the classes are centred there.
_STRESS_CLASSES = [
    (15.0, "#fef0d9", "rare (moins de 15 % des mois)"),
    (20.0, "#fdcc8a", "habituel (15 à 20 %)"),
    (25.0, "#fc8d59", "fréquent (20 à 25 %)"),
    ("inf", "#d7301f", "très fréquent (plus de 25 %)"),
]


def _qml(
    band: int,
    cmin: float,
    cmax: float,
    stops: list[tuple[float | str, str, str]],
    ramp: str = "INTERPOLATED",
) -> str:
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
        f'        <colorrampshader colorRampType="{ramp}" clip="0">\n'
        f"{items}\n"
        "        </colorrampshader>\n"
        "      </rastershader>\n"
        "    </rasterrenderer>\n"
        "  </pipe>\n"
        "</qgis>\n"
    )


def trend_qml() -> str:
    """Speed of change (Sen slope, NDVI/month): brown = dépérissement, green = verdissement."""
    return _qml(1, -0.005, 0.005, _TREND_CLASSES, "DISCRETE")


def trend_class_qml() -> str:
    """Significant trends only (Mann-Kendall): 'no significant trend' is left transparent."""
    return _paletted_qml(
        [
            (-1, "#8c510a", "dépérissement significatif"),
            (0, "#f5f5f5", "pas de tendance significative", 0),
            (1, "#1b7837", "verdissement significatif"),
        ]
    )


def break_year_qml(start: int, end: int) -> str:
    """Year of the break (Pettitt), one colour per year: light = early, dark = recent."""
    years = list(range(start, end + 1))
    last = max(1, len(years) - 1)
    return _paletted_qml(
        [
            (y, _blend("#fee391", "#8c2d04", i / last), f"rupture en {y}")
            for i, y in enumerate(years)
        ]
    )


def drought_qml() -> str:
    """Deviation from normal of the last year (z-score): red = drier, green = greener."""
    return _qml(1, -1.5, 1.5, _DROUGHT_CLASSES, "DISCRETE")


def stress_frequency_qml() -> str:
    """How often the vegetation was stressed (% of months): pale = rare, red = chronic."""
    return _qml(1, 0.0, 50.0, _STRESS_CLASSES, "DISCRETE")


def _blend(a: str, b: str, t: float) -> str:
    """Hex colour at ``t`` (0-1) on the straight line from ``a`` to ``b``."""
    ca, cb = (tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ca, cb, strict=True))


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


def _paletted_qml(entries: list[tuple]) -> str:
    """A paletted (categorical) raster QML: (value, colour, label[, alpha])."""
    items = "\n".join(
        f'        <paletteEntry value="{e[0]}" color="{e[1]}" label="{e[2]}"'
        f' alpha="{e[3] if len(e) > 3 else 255}"/>'
        for e in entries
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
