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
