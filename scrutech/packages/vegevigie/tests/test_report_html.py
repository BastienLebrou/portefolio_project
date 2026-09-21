"""HTML report: classes and colours follow the plugin QML, figures and sentences are right."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString

from vegevigie.report.html import build_report, class_shares, colorize, parse_qml

_STYLES = Path(__file__).resolve().parents[3] / "plugins" / "qgis" / "scrutech" / "algorithms"


def _plugin_styles():
    spec = importlib.util.spec_from_file_location("_styles_for_report", _STYLES / "_styles.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tif(path: Path, values: np.ndarray) -> None:
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=values.shape[1],
        height=values.shape[0],
        count=1,
        dtype="float32",
        crs="EPSG:2154",
        transform=from_origin(880_000, 6_476_000, 10, 10),
    ) as ds:
        ds.write(values.astype("float32"), 1)


def test_discrete_classes_hold_values_up_to_their_bound() -> None:
    legend = parse_qml(_plugin_styles().trend_qml())
    values = np.array([[-0.004, -0.003, 0.0, 0.002], [0.01, np.nan, 0.001, -0.002]])

    # net dép. (<= -0.003): 2 · léger dép.: 1 · stable (<= 0.001): 2 · léger verd.: 1 · net: 1
    assert np.allclose(class_shares(values, legend), [200 / 7, 100 / 7, 200 / 7, 100 / 7, 100 / 7])
    rgba = colorize(values, legend)
    assert tuple(rgba[0, 0]) == (0x8C, 0x51, 0x0A, 255)  # the QGIS colour of 'net dépérissement'
    assert rgba[1, 1, 3] == 0  # nodata stays transparent


def test_single_symbol_styles_give_their_colour() -> None:
    styles = _plugin_styles()
    assert parse_qml(styles.paff_line_qml()).entries[0][1] == "#b30000"
    assert parse_qml(styles.paff_zone_qml()).entries[0][1] == "#fc8d59"
    biotrame = parse_qml(styles.biotrame_qml())
    assert biotrame.kind == "DISCRETE" and biotrame.entries[-1][2] == "très forte (80 à 100)"
    assert class_shares(np.array([10.0, 50.0, 95.0, 100.0]), biotrame) == [25.0, 0, 25.0, 0, 50.0]


def test_report_summarises_every_tool_with_qgis_legends(tmp_path: Path) -> None:
    styles = _plugin_styles()
    out = tmp_path / "store"
    vv = out / "vegevigie" / "aoi=bbox-test" / "output"
    eco = out / "ecobuage" / "aoi=bbox-test" / "output"
    paf = out / "paf" / "aoi=bbox-test" / "output"
    for folder in (vv, eco, paf):
        folder.mkdir(parents=True)
    trend = np.full((10, 10), 0.0)
    trend[:2] = 0.01  # 20 % net verdissement
    trend[2:3] = -0.01  # 10 % net dépérissement
    _tif(vv / "trend_sen_slope_2021_2024.tif", trend)
    classes = np.zeros((10, 10))
    classes[:5] = 2  # 50 prioritaire pixels of 100 m² = 0.5 ha
    _tif(eco / "ecobuage_classes.tif", classes)
    line = LineString([(882_000, 6_474_000), (883_000, 6_474_000)])
    gpd.GeoDataFrame(geometry=[line], crs=2154).to_crs(4326).to_file(paf / "interface_line.geojson")

    html, tools = build_report(
        "bbox-test", (4.6, 44.55, 4.62, 44.56), styles.report_styles(), tmp_path / "r.html", out
    )

    page = html.read_text(encoding="utf-8")
    assert tools == ["VegeVigie", "PAFF", "Écobuage"]
    assert "net verdissement sur 20\u00a0% de la zone" in page
    assert "1,0\u00a0km" in page  # PAFF border length
    assert "prioritaire\u00a0: 0,5\u00a0ha" in page  # label : value, no agreement to get wrong
    assert "léger dépérissement" in page  # the full QGIS legend is shown
    assert "srcdoc=" in page and "leaflet" in page.lower()
    # Branded and self-contained: the ScruTech logo and Mantis travel inside the file.
    assert 'aria-label="Logo ScruTech' in page and "data:image/png;base64," in page


def test_report_without_analyses_says_what_to_do(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="Aucune analyse"):
        build_report("bbox-none", (0, 0, 1, 1), {}, tmp_path / "r.html", tmp_path)
