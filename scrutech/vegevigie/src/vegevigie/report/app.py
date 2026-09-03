"""ScruTech visual report (Streamlit) — one page summarising an analysis folder.

Reads the results folder from ``SCRUTECH_RESULTS`` and renders every pillar output it
finds: a shared map (biotrame hexagons, PAF interface, AlphaEarth change) plus raster
thumbnails (VegeVigie trend/drought, écobuage) and headline metrics. Launched from QGIS:

    SCRUTECH_RESULTS=<folder> streamlit run src/vegevigie/report/app.py
"""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import streamlit as st

from vegevigie.report.data import ReportInputs, discover

# classe → colour (biotrame alert palette: green → orange → red).
_CLASSE_COLOR = {0: "#cccccc", 1: "#fdae61", 2: "#d73027"}
_CLASSE_LABEL = {0: "secondaire", 1: "à étudier", 2: "prioritaire"}

st.set_page_config(page_title="ScruTech — rapport", page_icon="🛰️", layout="wide")
st.title("🛰️ ScruTech — rapport de diagnostic environnemental")


def _results() -> ReportInputs:
    folder = os.environ.get("SCRUTECH_RESULTS", ".")
    return discover(folder)


data = _results()
st.caption(f"Dossier de résultats : `{data.folder}`")

if not data.any():
    st.warning(
        "Aucune sortie ScruTech trouvée dans ce dossier. Lance d'abord un algorithme "
        "(biotrame, écobuage, VegeVigie, PAF, AlphaEarth) sur une emprise, puis recharge."
    )
    st.stop()

st.success("Piliers présents : " + ", ".join(data.present()))


def _metrics(data: ReportInputs) -> None:
    cols = st.columns(4)
    if data.biotrame:
        g = gpd.read_file(data.biotrame)
        cols[0].metric("Hexagones biotrame", len(g))
        cols[1].metric("Prioritaires", int((g.get("classe", 0) == 2).sum()))
    if data.interface_line:
        line = gpd.read_file(data.interface_line).to_crs("EPSG:2154")
        cols[2].metric("Frontière PAF (km)", round(float(line.length.sum()) / 1000, 2))
    if data.alphaearth_change:
        ch = gpd.read_file(data.alphaearth_change)
        changed = int(ch["changed"].sum()) if "changed" in ch else 0
        cols[3].metric("Pixels changés (AlphaEarth)", changed)


def _map(data: ReportInputs) -> None:
    import folium
    import leafmap.foliumap as leafmap

    layers = [
        p
        for p in (data.biotrame, data.interface_zone, data.interface_line, data.alphaearth_change)
        if p is not None
    ]
    if not layers:
        return
    bounds = gpd.read_file(layers[0]).to_crs("EPSG:4326").total_bounds
    m = leafmap.Map(center=[(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2], zoom=11)

    if data.biotrame:
        gdf = gpd.read_file(data.biotrame).to_crs("EPSG:4326")
        folium.GeoJson(
            gdf,
            name="Biotrame — priorité",
            style_function=lambda f: {
                "fillColor": _CLASSE_COLOR.get(int(f["properties"].get("classe", 0)), "#cccccc"),
                "color": "#555555",
                "weight": 0.4,
                "fillOpacity": 0.6,
            },
            tooltip=folium.GeoJsonTooltip(fields=[c for c in ("score", "classe") if c in gdf]),
        ).add_to(m)
    if data.interface_zone:
        old_style = {"fillColor": "#e34a33", "color": "#b30000", "fillOpacity": 0.5}
        folium.GeoJson(
            gpd.read_file(data.interface_zone).to_crs("EPSG:4326"),
            name="PAF — bande OLD",
            style_function=lambda f: old_style,
        ).add_to(m)
    if data.alphaearth_change:
        ch = gpd.read_file(data.alphaearth_change).to_crs("EPSG:4326")
        if "changed" in ch:
            ch = ch[ch["changed"]]
        folium.GeoJson(ch, name="AlphaEarth — changement").add_to(m)

    folium.LayerControl().add_to(m)
    m.to_streamlit(height=560)


def _raster_thumb(path: Path, title: str, cmap: str) -> None:
    import matplotlib.pyplot as plt
    import numpy as np
    import rasterio

    with rasterio.open(path) as ds:
        arr = ds.read(1).astype("float64")
        if ds.nodata is not None:
            # La valeur "nodata" (pixels hors zone d'analyse) est un simple nombre
            # convenu (souvent -9999) : on la remplace par NaN pour que matplotlib
            # l'affiche en transparent/vide plutôt que comme une fausse valeur.
            arr[arr == ds.nodata] = np.nan
    fig, ax = plt.subplots(figsize=(4, 3))
    im = ax.imshow(arr, cmap=cmap)
    ax.set_title(title, fontsize=9)
    ax.axis("off")
    fig.colorbar(im, ax=ax, shrink=0.7)
    st.pyplot(fig)


st.subheader("Métriques")
_metrics(data)

st.subheader("Carte")
_map(data)

rasters = [
    (data.trend, "VegeVigie — tendance (Sen)", "BrBG"),
    (data.drought, "VegeVigie — sécheresse", "RdYlGn"),
    (data.ecobuage_aptitude, "Écobuage — aptitude", "YlGn"),
    (data.ecobuage_classes, "Écobuage — classes", "viridis"),
]
present_rasters = [r for r in rasters if r[0] is not None]
if present_rasters:
    st.subheader("Couches raster")
    cols = st.columns(2)
    for i, (path, title, cmap) in enumerate(present_rasters):
        if path is None:
            continue
        with cols[i % 2]:
            _raster_thumb(path, title, cmap)

if data.biotrame:
    st.subheader("Répartition des classes biotrame")
    g = gpd.read_file(data.biotrame)
    if "classe" in g:
        counts = g["classe"].map(_CLASSE_LABEL).value_counts()
        st.bar_chart(counts)
