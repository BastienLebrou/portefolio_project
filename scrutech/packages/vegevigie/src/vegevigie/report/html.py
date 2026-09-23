"""ScruTech visual report: one self-contained HTML page for an area of interest.

Reads the outputs cached for the area (see :mod:`vegevigie.report.data`) and writes a single
.html file in three parts: key figures ("En bref"), a map whose layers switch on and off, and
plain-French sentences per tool. Colours and legends are parsed from the QML styles the QGIS
plugin applies, so the page and QGIS always agree. No server: the file opens in any browser,
can be mailed and printed to PDF. Only the map needs internet (Leaflet and the basemaps).
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from vegevigie.report.data import ReportInputs, discover

_ORTHO = (
    "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/jpeg"
    "&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
)
_MAX_PX = 2000  # longest side of a map overlay: keeps the page light enough to mail
_MAP_NOTE = (
    "Cochez les couches en haut à droite de la carte. La carte a besoin d'internet ; les "
    "chiffres et les phrases s'affichent sans connexion."
)
_FOOTER = "Rapport généré par ScruTech à partir des analyses enregistrées pour la zone {}."
_GUIDE = (
    "J'ai lu les couches de la zone pour vous : voici, analyse par analyse, ce qu'elles "
    "montrent. Ces chiffres orientent une visite de terrain, ils ne la remplacent pas."
)

# ScruTech brand (see the brand folder README): palette, type, logo, emblem and Mantis sprite
# (quantized to 32 colours, 21 KB). The fonts need internet; offline, the fallbacks apply.
_BRAND = Path(__file__).resolve().parent / "brand"
_FONTS = (
    "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;"
    "12..96,800&amp;family=IBM+Plex+Mono:wght@400;500&amp;family=IBM+Plex+Sans:wght@400;500;600"
    "&amp;family=Silkscreen&amp;display=swap"
)
_CSS = """
:root {
  --creme: #F1E8D2; --papier: #FBF7EC; --bordeaux: #661C1A; --brique: #B23F2C;
  --olive: #5C6A30; --olive-fonce: #37401D; --encre: #2B261D; --doux: #6B6150;
  --trait: rgba(55, 64, 29, .18);
  --titre: "Bricolage Grotesque", "Arial Black", Arial, sans-serif;
  --corps: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", Consolas, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--creme); color: var(--encre); font: 16px/1.6 var(--corps);
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
main { max-width: 1000px; margin: 0 auto; padding: 28px 16px 48px; }
.masthead { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 32px; }
.logo svg { display: block; width: 400px; max-width: 100%; height: auto; }
.title { flex: 1 1 280px; }
.eyebrow { margin: 0; font: 500 .8rem/1.4 var(--mono); letter-spacing: .12em;
  text-transform: uppercase; color: var(--olive); }
h1 { margin: 2px 0 8px; font: 800 2.1rem/1.1 var(--titre); color: var(--bordeaux); }
.meta { margin: 0; font: .85rem/1.5 var(--mono); color: var(--doux); }
.card { margin-top: 20px; padding: 20px 24px 24px; background: var(--papier);
  border: 1px solid var(--trait); border-radius: 12px; }
h2 { margin: 0 0 16px; font: 700 1.35rem/1.2 var(--titre); color: var(--bordeaux); }
h3 { margin: 0 0 4px; font: 700 1.05rem/1.3 var(--titre); color: var(--olive-fonce); }
h4 { margin: 0 0 6px; font: 600 .9rem/1.3 var(--corps); color: var(--olive-fonce); }
p { margin: 0 0 8px; }
.figures { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px; }
.figure { padding: 4px 0 4px 14px; border-left: 3px solid var(--brique); }
.figure .tool { margin: 0 0 2px; font: 500 .75rem/1.4 var(--mono); letter-spacing: .06em;
  text-transform: uppercase; color: var(--olive); }
.figure .value { margin: 0; font: 600 1rem/1.45 var(--corps); }
.figure .value::first-letter { text-transform: uppercase; }
.map { width: 100%; height: 540px; background: var(--creme); border: 1px solid var(--trait);
  border-radius: 8px; }
.note { margin: 8px 0 0; font-size: .85rem; color: var(--doux); }
.legends { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px; margin-top: 16px; }
.legend ul { margin: 0; padding: 0; list-style: none; font-size: .86rem; }
.legend li { margin: 2px 0; }
.swatch { display: inline-block; width: 14px; height: 14px; margin-right: 8px;
  vertical-align: -2px; border: 1px solid rgba(43, 38, 29, .25); border-radius: 2px; }
.guide { display: flex; align-items: center; gap: 18px; margin-bottom: 8px; padding: 14px 18px;
  background: var(--creme); border-radius: 10px; }
.guide p { margin: 0; }
.mantis { flex: none; width: 120px; height: auto; }
.name { display: block; font: .8rem/1.5 "Silkscreen", var(--mono); color: var(--brique); }
article { padding: 14px 0 6px; border-top: 1px solid var(--trait); }
article:first-of-type { border-top: 0; }
footer { display: flex; align-items: center; gap: 16px; margin-top: 28px; font-size: .85rem;
  color: var(--doux); }
footer p { margin: 0; }
.emblem svg { display: block; width: 52px; height: auto; }
.signature { font: 500 .85rem/1.4 var(--mono); color: var(--olive-fonce); }
@media (max-width: 600px) {
  .card { padding: 16px; } h1 { font-size: 1.7rem; } .map { height: 420px; }
  .guide { flex-direction: column; align-items: flex-start; }
}
@media print {
  body { background: #fff; } main { padding: 0; } .card { break-inside: avoid; }
  .map { height: 480px; }
}
"""


@dataclass(frozen=True)
class Legend:
    """A style reduced to (value, colour, label, alpha) entries, ordered as in QGIS.

    ``kind`` DISCRETE: a class holds the values up to its bound; INTERPOLATED: colours blend
    between stops; EXACT: one colour per value (paletted raster, categorized vector).
    """

    kind: str
    entries: list[tuple[float, str, str, int]]


def parse_qml(qml: str) -> Legend:
    """Legend of a ScruTech QML style (pseudocolor, paletted, categorized or graduated)."""
    root = ET.fromstring(re.sub(r"<!DOCTYPE[^>]*>", "", qml))
    shader = root.find(".//colorrampshader")
    if shader is not None:
        items, kind = list(shader.iter("item")), shader.get("colorRampType", "INTERPOLATED")
    else:
        items, kind = list(root.iter("paletteEntry")), "EXACT"
    entries = [
        (
            float(i.get("value", "nan")),
            i.get("color", ""),
            i.get("label", ""),
            int(i.get("alpha", 255)),
        )
        for i in items
    ]
    colours = {s.get("name"): _symbol_colour(s) for s in root.iter("symbol")}
    for cat in root.iter("category"):
        colour, alpha = colours.get(cat.get("symbol"), ("#000000", 255))
        entries.append((float(cat.get("value", "nan")), colour, cat.get("label", ""), alpha))
    for rng in root.iter("range"):  # graduated: a class holds the values up to its upper bound
        kind = "DISCRETE"
        colour, alpha = colours.get(rng.get("symbol"), ("#000000", 255))
        entries.append((float(rng.get("upper", "nan")), colour, rng.get("label", ""), alpha))
    if not entries and colours:  # single symbol: one colour for the whole layer
        colour, alpha = next(iter(colours.values()))
        entries.append((0.0, colour, "", alpha))
    return Legend(kind, entries)


def _symbol_colour(symbol: ET.Element) -> tuple[str, int]:
    """Hex colour and alpha of a QML symbol (fill ``color`` or line ``line_color``)."""
    option = symbol.find(".//Option[@name='color']")
    if option is None:
        option = symbol.find(".//Option[@name='line_color']")
    rgba = option.get("value", "0,0,0,255") if option is not None else "0,0,0,255"
    r, g, b, a = (int(c) for c in rgba.split(","))
    return f"#{r:02x}{g:02x}{b:02x}", a


def class_index(values: np.ndarray, legend: Legend) -> np.ndarray:
    """Legend class of each pixel (position in ``legend.entries``), -1 where none applies."""
    idx = np.full(values.shape, -1)
    valid = np.isfinite(values)
    if legend.kind == "DISCRETE":
        for i, (bound, *_rest) in reversed(list(enumerate(legend.entries))):
            idx[valid & (values <= bound)] = i
    else:
        for i, (value, *_rest) in enumerate(legend.entries):
            idx[valid & (values == value)] = i
    return idx


def class_shares(values: np.ndarray, legend: Legend) -> list[float]:
    """Share (%) of the classified pixels in each legend class."""
    idx = class_index(values, legend)
    total = np.count_nonzero(idx >= 0)
    return [
        100.0 * np.count_nonzero(idx == i) / total if total else 0.0
        for i in range(len(legend.entries))
    ]


def colorize(values: np.ndarray, legend: Legend) -> np.ndarray:
    """RGBA image of ``values`` coloured as QGIS draws them (no class = transparent)."""
    table = np.array([[*_rgb(c), a] for _v, c, _l, a in legend.entries], dtype=float)
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if legend.kind == "INTERPOLATED":
        valid = np.isfinite(values)
        stops = [v for v, *_rest in legend.entries]
        for k in range(4):
            rgba[..., k][valid] = np.interp(values[valid], stops, table[:, k])
        return rgba
    idx = class_index(values, legend)
    rgba[idx >= 0] = table[idx[idx >= 0]]
    return rgba


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


# --- the page ------------------------------------------------------------------------------
@dataclass
class _Parts:
    """What each tool contributes: a figures row, sentences, and map layers with a legend."""

    figures: list[tuple[str, str]] = field(default_factory=list)
    sentences: list[tuple[str, list[str]]] = field(default_factory=list)
    layers: list[tuple[Any, str, Legend]] = field(default_factory=list)


def build_report(
    aoi_id: str,
    bbox: tuple[float, float, float, float],
    styles: dict[str, str] | None,
    out_path: str | Path,
    root: str | Path | None = None,
) -> tuple[Path, list[str]]:
    """Write the HTML report of an AOI; returns its path and the tools it covers.

    ``styles`` maps an output-name prefix to its QML (the plugin's own styles).
    """
    from core.storage import data_root

    data = discover(root or data_root(), aoi_id)
    if not data.any():
        raise ValueError(
            f"Aucune analyse enregistrée pour cette zone ({aoi_id}). Lancez d'abord un outil "
            "du groupe 2, ou reprenez exactement la même emprise que l'analyse."
        )
    from vegevigie.styles import report_styles

    legends = {prefix: parse_qml(qml) for prefix, qml in (styles or report_styles()).items()}

    def legend_for(path: Path | None) -> Legend | None:
        if path is None:
            return None
        return next((lg for prefix, lg in legends.items() if path.name.startswith(prefix)), None)

    parts = _Parts()
    for add in (_vegevigie, _paff, _ecobuage, _biotrame, _alphaearth, _projection):
        add(data, legend_for, parts)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_page(aoi_id, bbox, data, parts), encoding="utf-8")
    return out, data.present()


def _vegevigie(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    sentences: list[str] = []
    if (lg := legend_for(data.trend)) and data.trend:
        start, end = data.trend.stem.split("_")[-2:]
        shares = class_shares(_read(data.trend)[0], lg)
        low, high = lg.entries[0][2], lg.entries[-1][2]
        parts.figures.append(
            (
                f"Végétation {start}-{end}",
                f"{high} : {_pct(shares[-1])} · {low} : {_pct(shares[0])}",
            )
        )
        sentences.append(
            f"Entre {start} et {end}, la végétation montre un {high} sur {_pct(shares[-1])} de "
            f"la zone et un {low} sur {_pct(shares[0])}."
        )
        parts.layers.append(
            (_raster(data.trend, lg, "Vitesse d'évolution"), "Vitesse d'évolution", lg)
        )
    if (lg := legend_for(data.trend_class)) and data.trend_class:
        shares = class_shares(_read(data.trend_class)[0], lg)
        sentences.append(
            f"Le test de Mann-Kendall confirme un {lg.entries[0][2]} sur {_pct(shares[0])} de la "
            f"zone et un {lg.entries[-1][2]} sur {_pct(shares[-1])}."
        )
        name = "Tendances significatives"
        parts.layers.append((_raster(data.trend_class, lg, name), name, lg))
    if (lg := legend_for(data.drought)) and data.drought:
        year = data.drought.stem.split("_")[-1]
        shares = class_shares(_read(data.drought)[0], lg)
        mid = len(shares) // 2
        below, above = sum(shares[:mid]), sum(shares[mid + 1 :])
        parts.figures.append(
            (
                f"Écart à la normale en {year}",
                f"en dessous : {_pct(below)} · au-dessus : {_pct(above)}",
            )
        )
        sentences.append(
            f"En {year}, la végétation est moins verte que la normale sur {_pct(below)} de la "
            f"zone et plus verte sur {_pct(above)}."
        )
        name = f"Écart à la normale {year}"
        parts.layers.append((_raster(data.drought, lg, name), name, lg))
    if (lg := legend_for(data.stress)) and data.stress:
        shares = class_shares(_read(data.stress)[0], lg)
        half = len(shares) // 2
        often, bound = sum(shares[half:]), lg.entries[half - 1][0]
        parts.figures.append(
            ("Stress de la végétation", f"stress fréquent : {_pct(often)} de la zone")
        )
        sentences.append(
            f"La végétation a souvent souffert (plus de {_num(bound)} % des mois) sur "
            f"{_pct(often)} de la zone."
        )
        name = "Fréquence de stress"
        parts.layers.append((_raster(data.stress, lg, name), name, lg))
    if data.zonal:
        sentences.extend(_worst_communes(data.zonal))
    if sentences:
        parts.sentences.append(("Végétation (VegeVigie)", sentences))


def _worst_communes(parquet: Path) -> list[str]:
    import pandas as pd

    stats = pd.read_parquet(parquet)
    if not {"nom", "pct_browning"} <= set(stats.columns):
        return []
    top = stats[stats["pct_browning"] > 0].nlargest(3, "pct_browning")
    if top.empty:
        return []
    names = ", ".join(f"{row.nom} ({_pct(row.pct_browning)})" for row in top.itertuples())
    return [f"Communes les plus touchées par le dépérissement : {names}."]


def _paff(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    if data.interface_line is None:
        return
    import folium
    import geopandas as gpd

    line = gpd.read_file(data.interface_line)
    line_colour = _colour(legend_for(data.interface_line), "#b30000")
    km = float(line.to_crs(2154).length.sum()) / 1000
    figures = f"frontière : {_num(km, 1)} km"
    sentences = [f"La frontière entre la forêt et les habitations mesure {_num(km, 1)} km."]
    if data.interface_zone:
        zone = gpd.read_file(data.interface_zone)
        ha = float(zone.to_crs(2154).area.sum()) / 10_000
        figures += f" · à débroussailler : {_num(ha, 1)} ha"
        sentences.append(f"La bande à débroussailler autour des maisons couvre {_num(ha, 1)} ha.")
        band_colour = _colour(legend_for(data.interface_zone), "#fc8d59")
        band_legend = Legend("EXACT", [(1, band_colour, "bande de débroussaillement", 255)])
        style = {"fillColor": band_colour, "color": band_colour, "weight": 0, "fillOpacity": 0.6}
        band = folium.GeoJson(
            zone[["geometry"]].to_crs(4326), name="PAFF : bande", style_function=lambda _f: style
        )
        parts.layers.append((band, "PAFF : bande de débroussaillement", band_legend))
    line_style = {"color": line_colour, "weight": 3}
    border = folium.GeoJson(
        line[["geometry"]].to_crs(4326),
        name="PAFF : frontière",
        style_function=lambda _f: line_style,
    )
    line_legend = Legend("EXACT", [(0, line_colour, "frontière habitat-forêt", 255)])
    parts.layers.append((border, "PAFF : frontière habitat-forêt", line_legend))
    parts.figures.append(("Interface habitat-forêt", figures))
    parts.sentences.append(("Risque incendie (PAFF)", sentences))


def _ecobuage(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    if (lg := legend_for(data.ecobuage_classes)) and data.ecobuage_classes:
        values, pixel_ha = _read(data.ecobuage_classes)
        idx = class_index(values, lg)
        shares = class_shares(values, lg)
        ha = [np.count_nonzero(idx == i) * (pixel_ha or 0.0) for i in range(len(shares))]
        best, next_ = lg.entries[-1][2], lg.entries[-2][2]
        parts.figures.append(("Écobuage", f"{best} : {_ha(ha[-1])} · {next_} : {_ha(ha[-2])}"))
        sentence = (
            f"{_pct(shares[-1])} de la zone ({_ha(ha[-1])}) est {best} pour l'écobuage et "
            f"{_pct(shares[-2])} ({_ha(ha[-2])}) {next_}, compte tenu de la pente, de "
            "l'accès et des bâtiments."
        )
        parts.sentences.append(("Écobuage (PAFF)", [sentence]))
        name = "Écobuage : classes"
        parts.layers.append((_raster(data.ecobuage_classes, lg, name), name, lg))
    if (lg := legend_for(data.ecobuage_aptitude)) and data.ecobuage_aptitude:
        name = "Écobuage : aptitude"
        parts.layers.append((_raster(data.ecobuage_aptitude, lg, name), name, lg))


def _biotrame(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    if (lg := legend_for(data.biotrame)) is None or data.biotrame is None:
        return
    import folium
    import geopandas as gpd

    hexes = gpd.read_file(data.biotrame)
    idx = class_index(hexes["score"].to_numpy(dtype=float), lg)
    counts = [int((idx == i).sum()) for i in range(len(lg.entries))]
    names = [label.split(" (")[0] for _v, _c, label, _a in lg.entries]  # "forte (60 à 80)"
    total = len(hexes)
    parts.figures.append(
        (
            "Biotrame",
            f"priorité {names[-1]} : {counts[-1]} · {names[-2]} : {counts[-2]} sur {total}",
        )
    )
    parts.sentences.append(
        (
            "Trame verte et bleue (Biotrame)",
            [
                f"Sur {total} hexagones, {counts[-1]} ont une priorité {names[-1]} et "
                f"{counts[-2]} une priorité {names[-2]} pour la continuité écologique. La note "
                f"médiane est de {_num(float(hexes['score'].median()))} sur 100."
            ],
        )
    )
    hexes["priorite"] = [names[i] if i >= 0 else "" for i in idx]
    hexes["couleur"] = [lg.entries[i][1] if i >= 0 else "#cccccc" for i in idx]
    hexes["note"] = hexes["score"].round(0)
    layer = folium.GeoJson(
        hexes[["priorite", "note", "couleur", "geometry"]].to_crs(4326),
        name="Biotrame",
        show=False,
        style_function=lambda f: {
            "fillColor": f["properties"]["couleur"],
            "color": "#5a5a5a",
            "weight": 0.3,
            "fillOpacity": 0.5,  # as in QGIS: the habitats stay visible underneath
        },
        tooltip=folium.GeoJsonTooltip(fields=["priorite", "note"], aliases=["Priorité", "Note"]),
    )
    parts.layers.append((layer, "Biotrame : priorité", lg))


def _alphaearth(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    if data.alphaearth_change is None:
        return
    import folium
    import geopandas as gpd

    year1, year2 = data.alphaearth_change.stem.split("_")[-2:]
    points = gpd.read_file(data.alphaearth_change)
    changed = points[points["changed"].astype(bool)] if "changed" in points else points.iloc[:0]
    parts.figures.append(
        ("Changements AlphaEarth", f"changements marqués : {len(changed)} points sur {len(points)}")
    )
    parts.sentences.append(
        (
            "Changements de paysage (AlphaEarth)",
            [
                f"Entre {year1} et {year2}, {len(changed)} des {len(points)} points "
                "échantillonnés montrent les changements les plus marqués ; à vérifier sur les "
                "photographies aériennes."
            ],
        )
    )
    colour = "#7b3294"
    layer = folium.GeoJson(
        changed[["geometry"]].to_crs(4326),
        name="AlphaEarth",
        show=False,
        marker=folium.CircleMarker(radius=4, color=colour, fill=True, fill_opacity=0.9),
    )
    lg = Legend("EXACT", [(1, colour, "changement marqué", 255)])
    parts.layers.append((layer, f"AlphaEarth : changements {year1}-{year2}", lg))


_CLIMATE_LABELS = {
    "jours_chauds": "Jours à plus de 30 °C par an",
    "periode_seche": "Plus longue période sans pluie, en jours",
    "jours_feu": "Jours propices aux feux par an",
}


def _projection(data: ReportInputs, legend_for: Callable, parts: _Parts) -> None:
    if data.projection is None:
        return
    import json

    summary = json.loads(data.projection.read_text(encoding="utf-8"))
    horizons = sorted(summary["hazard_increase"], key=int)
    last = horizons[-1]
    sentences = []
    for name, by_year in summary["indicators"].items():
        path = ", ".join(f"{_num(by_year[y][0])} en {y}" for y in horizons)
        low, high = by_year[last][1], by_year[last][2]
        sentences.append(
            f"{_CLIMATE_LABELS.get(name, name)} : {_num(by_year['2025'][0])} aujourd'hui, puis "
            f"{path} (de {_num(low)} à {_num(high)} en {last} selon les modèles)."
        )
    hot = summary["indicators"].get("jours_chauds")
    if hot:
        parts.figures.append(
            (
                f"Climat en {last}",
                f"jours à plus de 30 °C : {_num(hot['2025'][0])} aujourd'hui, "
                f"{_num(hot[last][0])} en {last}",
            )
        )

    folder = data.projection.parent
    strong = {}
    for year in ["2025", *horizons]:
        tif = folder / f"exposition_{year}.tif"
        if not tif.is_file() or (lg := legend_for(tif)) is None:
            continue
        shares = class_shares(_read(tif)[0], lg)
        strong[year] = sum(shares[-2:])  # forte + très forte
        name = "Exposition aujourd'hui" if year == "2025" else f"Exposition {year}"
        parts.layers.append((_raster(tif, lg, name), name, lg))
    if "2025" in strong and last in strong:
        steps = ", ".join(f"{_pct(strong[y])} en {y}" for y in horizons if y in strong)
        parts.figures.append(
            (
                "Zone la plus exposée",
                f"forte ou très forte : {_pct(strong['2025'])} aujourd'hui, "
                f"{_pct(strong[last])} en {last}",
            )
        )
        sentences.append(
            f"Part de la zone en exposition forte ou très forte : {_pct(strong['2025'])} "
            f"aujourd'hui, puis {steps}. Ce sont les secteurs où la végétation est déjà "
            "stressée ou en déclin, que le climat plus chaud et plus sec touchera en premier."
        )
    trend = next(iter(sorted(folder.glob("ndvi_tendance_*.tif"))), None)
    if trend is not None and (lg := legend_for(trend)) is not None:
        year = trend.stem.split("_")[-1]
        shares = class_shares(_read(trend)[0], lg)
        sentences.append(
            f"Si la tendance observée se poursuit, le NDVI baisserait d'ici {year} sur "
            f"{_pct(sum(shares[:2]))} des secteurs à tendance significative et augmenterait sur "
            f"{_pct(sum(shares[-2:]))}."
        )
        name = f"NDVI {year} si la tendance continue"
        parts.layers.append((_raster(trend, lg, name), name, lg))
    sentences.append(
        f"Méthode : projections climatiques CMIP6 de {len(summary['models'])} modèles au "
        "centre de la zone (Open-Meteo, maille de 10 km, licence CC BY 4.0), recalées sur la "
        "trajectoire de réchauffement de référence (TRACC : +2 °C en 2030 et +2,7 °C en 2050 "
        "pour la France). Ce sont des ordres de grandeur, pas des prévisions."
    )
    parts.sentences.append(("Climat futur (projection)", sentences))


def _colour(legend: Legend | None, default: str) -> str:
    return legend.entries[0][1] if legend and legend.entries else default


def _read(path: Path) -> tuple[np.ndarray, float | None]:
    """Band 1 as floats (nodata = NaN) and the pixel area in hectares (None if unknown)."""
    import rasterio

    with rasterio.open(path) as ds:
        values = ds.read(1, masked=True).astype("float64").filled(np.nan)
        projected = ds.crs is not None and ds.crs.is_projected
        pixel_ha = abs(ds.transform.a * ds.transform.e) / 10_000 if projected else None
    return values, pixel_ha


def _raster(path: Path, legend: Legend, name: str) -> Any:
    """The raster coloured as in QGIS, warped to Web Mercator, as a Leaflet image layer."""
    import folium
    import rasterio
    from affine import Affine
    from rasterio.transform import array_bounds
    from rasterio.warp import Resampling, calculate_default_transform, reproject, transform_bounds

    with rasterio.open(path) as ds:
        transform, width, height = calculate_default_transform(
            ds.crs, "EPSG:3857", ds.width, ds.height, *ds.bounds
        )
        scale = max(width, height) / _MAX_PX
        if scale > 1:
            width, height = max(1, int(width / scale)), max(1, int(height / scale))
            transform = transform * Affine.scale(scale)
        warped = np.full((height, width), np.nan)
        reproject(
            ds.read(1, masked=True).astype("float64").filled(np.nan),
            warped,
            src_transform=ds.transform,
            src_crs=ds.crs,
            dst_transform=transform,
            dst_crs="EPSG:3857",
            src_nodata=np.nan,
            dst_nodata=np.nan,
            resampling=Resampling.nearest,
        )
    west, south, east, north = transform_bounds(
        "EPSG:3857", "EPSG:4326", *array_bounds(height, width, transform)
    )
    return folium.raster_layers.ImageOverlay(
        colorize(warped, legend),
        bounds=[[south, west], [north, east]],
        name=name,
        opacity=0.85,
        show=False,
    )


def _map(bbox: tuple[float, float, float, float], parts: _Parts) -> str:
    import folium

    fmap = folium.Map(tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Plan (OpenStreetMap)").add_to(fmap)
    folium.TileLayer(
        _ORTHO, attr="IGN Géoplateforme", name="Photographies aériennes (IGN)", max_zoom=19
    ).add_to(fmap)
    for i, (layer, _name, _legend) in enumerate(parts.layers):
        layer.show = i == 0  # the first layer is on, the others one click away
        layer.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)
    west, south, east, north = bbox
    fmap.fit_bounds([[south, west], [north, east]])
    return fmap.get_root().render()


def _page(
    aoi_id: str, bbox: tuple[float, float, float, float], data: ReportInputs, parts: _Parts
) -> str:
    import base64

    import geopandas as gpd
    from shapely.geometry import box

    km2 = float(gpd.GeoSeries([box(*bbox)], crs=4326).to_crs(2154).area.iloc[0]) / 1e6
    e = html.escape
    logo = (_BRAND / "scrutech-logo.svg").read_text(encoding="utf-8")
    emblem = (_BRAND / "mantis-emblem.svg").read_text(encoding="utf-8")
    mantis = base64.b64encode((_BRAND / "mantis.png").read_bytes()).decode("ascii")
    favicon = base64.b64encode(emblem.encode("utf-8")).decode("ascii")

    figures = "".join(
        f"<div class='figure'><p class='tool'>{e(tool)}</p><p class='value'>{e(_typo(text))}</p>"
        "</div>"
        for tool, text in parts.figures
    )
    reading = "".join(
        f"<article><h3>{e(tool)}</h3>"
        + "".join(f"<p>{e(_typo(s))}</p>" for s in sentences)
        + "</article>"
        for tool, sentences in parts.sentences
    )
    legends = "".join(
        f"<div class='legend'><h4>{e(name)}</h4><ul>"
        + "".join(
            f"<li><span class='swatch' style='background:{c};opacity:{a / 255:.2f}'></span>"
            f"{e(label)}</li>"
            for _v, c, label, a in legend.entries
        )
        + "</ul></div>"
        for _layer, name, legend in parts.layers
    )
    map_block = ""
    if parts.layers:
        map_block = (
            "<section class='card'><h2>Carte</h2>"
            f"<iframe class='map' title='Carte' srcdoc=\"{e(_map(bbox, parts), quote=True)}\">"
            "</iframe><p class='note'>"
            + e(_typo(_MAP_NOTE))
            + f"</p><div class='legends'>{legends}</div></section>"
        )
    zone = _typo(f"Emprise de {_num(km2, 1)} km² · {date.today():%d/%m/%Y}")
    tools = _typo("Analyses : " + ", ".join(data.present()))
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Diagnostic ScruTech</title>
<link rel="icon" href="data:image/svg+xml;base64,{favicon}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_FONTS}">
<style>{_CSS}</style>
</head>
<body>
<main>
<header class="masthead">
<div class="logo">{logo}</div>
<div class="title">
<p class="eyebrow">Diagnostic de territoire</p>
<h1>Rapport de la zone</h1>
<p class="meta">{e(zone)}</p>
<p class="meta">{e(tools)}</p>
</div>
</header>
<section class="card"><h2>En bref</h2><div class="figures">{figures}</div></section>
{map_block}
<section class="card"><h2>Lecture des résultats</h2>
<div class="guide"><img class="mantis" alt="Mantis, la mascotte de ScruTech"
 src="data:image/png;base64,{mantis}"><p><span class="name">Mantis</span>{e(_typo(_GUIDE))}</p>
</div>
{reading}
</section>
<footer><div class="emblem">{emblem}</div><div><p class="signature">ScruTech · voir ce que
 l'œil ne voit pas</p><p>{e(_typo(_FOOTER.format(aoi_id)))}</p></div></footer>
</main>
</body>
</html>
"""


def _num(value: float, digits: int = 0) -> str:
    """French number: 1 234,5."""
    return f"{value:,.{digits}f}".replace(",", "\u202f").replace(".", ",")


def _pct(value: float) -> str:
    return _num(value, 1 if 0 < value < 10 else 0) + " %"


def _ha(value: float) -> str:
    return _num(value, 1 if value < 10 else 0) + " ha"


def _typo(text: str) -> str:
    """French typography: non-breaking spaces before : ; ! ? % » and units, and after «."""
    text = re.sub(r"(?<=\d) (?=km|ha)", "\u00a0", text)
    return re.sub(r" ([:;!?%»])", "\u00a0\\1", text).replace("« ", "«\u00a0")
