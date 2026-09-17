"""VegeVigie dashboard (M7) — Streamlit + leafmap.

Reads the pipeline's commune outputs from ``data/processed`` and shows: a trend
choropleth (green = greening, red = browning) with click-to-inspect commune
stats, a DuckDB-backed ranking table, and the AOI drought timeline. Degrades to a
clear "run the pipeline first" message when no outputs exist yet.

Launch via ``vegevigie dashboard`` (sets ``VEGEVIGIE_DATA_DIR``) or directly with
``streamlit run src/vegevigie/dashboard/app.py`` from the repo root.
"""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import leafmap.foliumap as leafmap
import pandas as pd
import streamlit as st

from vegevigie.config import load_settings
from vegevigie.dashboard.data import find_outputs, slope_color
from vegevigie.store import rank_communes

# Rank label -> (DuckDB column, ascending). Ascending surfaces browning / driest.
RANKINGS = {
    "Top greening": ("mean_sen_slope", False),
    "Top browning": ("mean_sen_slope", True),
    "Most drought-stressed": ("mean_anomaly", True),
}


def _processed_dir() -> Path:
    env = os.environ.get("VEGEVIGIE_DATA_DIR")
    return Path(env) if env else load_settings().paths.processed


st.set_page_config(page_title="VegeVigie", page_icon="🌿", layout="wide")
st.title("🌿 VegeVigie — vegetation trend & drought, commune by commune")

processed = _processed_dir()
out = find_outputs(processed)

if not out.ready():
    st.info(
        f"No pipeline outputs found in `{processed}`.\n\n"
        "Run a real analysis with `vegevigie run --small`, or generate a synthetic "
        "demo with `python scripts/demo_dashboard_data.py`, then reload."
    )
    st.stop()

gdf = gpd.read_parquet(out.zonal).to_crs("EPSG:4326")

c1, c2, c3 = st.columns(3)
c1.metric("Communes", len(gdf))
c2.metric("Greening", int((gdf["mean_sen_slope"] > 0).sum()))
c3.metric("Browning", int((gdf["mean_sen_slope"] < 0).sum()))

minx, miny, maxx, maxy = gdf.total_bounds
fmap = leafmap.Map(center=[(miny + maxy) / 2, (minx + maxx) / 2], zoom=9)


def _style(feature: dict) -> dict:
    return {
        "fillColor": slope_color(feature["properties"].get("mean_sen_slope")),
        "color": "#333333",
        "weight": 0.6,
        "fillOpacity": 0.75,
    }


fmap.add_gdf(gdf, layer_name="Trend (Sen's slope)", style_callback=_style, info_mode="on_click")
fmap.to_streamlit(height=520)

left, right = st.columns(2)
with left:
    st.subheader("Commune ranking")
    if out.duckdb is not None:
        choice = st.selectbox("Rank by", list(RANKINGS))
        column, ascending = RANKINGS[choice]
        st.dataframe(
            rank_communes(out.duckdb, metric=column, ascending=ascending, limit=10),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.dataframe(gdf.drop(columns="geometry"), hide_index=True, use_container_width=True)

with right:
    st.subheader("Drought timeline — AOI mean NDVI anomaly")
    if out.timeline is not None:
        timeline = pd.read_parquet(out.timeline)
        st.line_chart(timeline, x="time", y="anomaly_mean", height=360)
        st.caption("Negative = browner than the seasonal normal (drought stress).")
    else:
        st.caption("No drought-timeline output found.")
