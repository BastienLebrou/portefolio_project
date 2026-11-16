"""Static figures for the report: situation map and IGN orthophoto of the footprint."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")  # no display needed: figures are only written to PNG
import matplotlib.pyplot as plt  # noqa: E402
from core.sources import fetch_ortho  # noqa: E402

logger = logging.getLogger("biodiag")

LAYER_COLORS = {
    "znieff1": "#8e44ad",
    "znieff2": "#2980b9",
    "natura2000_zps": "#27ae60",
    "natura2000_sic": "#27ae60",
    "apb": "#c0392b",
    "rnn": "#d35400",
    "rnr": "#d35400",
    "pn": "#16a085",
    "pnr": "#16a085",
}
STAKE_COLORS = {"Faible": "#2e9e44", "Modéré": "#f39c12", "Fort": "#d62728"}


def situation_map(zip_, zer, zee, reservoirs: gpd.GeoDataFrame, occ: gpd.GeoDataFrame, path: Path):
    """Footprint, ZER/ZEE rings, protected areas and observations coloured by stake."""
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    handles = []
    for kind in reservoirs.kind.unique():
        sub = reservoirs[reservoirs.kind == kind]
        col = LAYER_COLORS.get(kind, "#888888")
        sub.plot(ax=ax, color=col, alpha=0.22, edgecolor=col, linewidth=0.8)
        handles.append(plt.Rectangle((0, 0), 1, 1, color=col, alpha=0.4, label=sub["type"].iloc[0]))
    for geom, col in [(zee, "#1f78ff"), (zer, "#ff8c00")]:
        gpd.GeoSeries([geom]).plot(
            ax=ax, facecolor="none", edgecolor=col, linestyle="--", linewidth=1.3
        )
    for level in ["Faible", "Modéré", "Fort"]:
        d = occ[occ.enjeu == level]
        ax.scatter(
            d.geometry.x,
            d.geometry.y,
            s=4 if level == "Faible" else 9,
            c=STAKE_COLORS[level],
            alpha=0.45 if level == "Faible" else 0.8,
            linewidths=0,
        )
    gpd.GeoSeries([zip_]).plot(ax=ax, color="#8b0000", edgecolor="#8b0000", linewidth=2)
    lines = [
        plt.Line2D([], [], color="#8b0000", lw=3, label="Emprise"),
        plt.Line2D([], [], color="#ff8c00", ls="--", label="ZER"),
        plt.Line2D([], [], color="#1f78ff", ls="--", label="ZEE"),
    ]
    dots = [
        plt.Line2D(
            [], [], marker="o", ls="", color=STAKE_COLORS[n], markersize=4, label=f"Obs. enjeu {n}"
        )
        for n in ["Fort", "Modéré", "Faible"]
    ]
    ax.legend(
        handles=lines + handles + dots,
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=7,
        frameon=False,
    )
    ax.set_aspect("equal")
    ax.set_axis_off()
    minx, miny, maxx, maxy = zee.bounds
    ax.set_xlim(minx - 200, maxx + 200)
    ax.set_ylim(miny - 200, maxy + 200)
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def orthophoto(aoi_gdf: gpd.GeoDataFrame, zip_, path: Path, margin_m: float = 250) -> bool:
    """IGN aerial photo around the footprint with its outline; False if the WMS is unavailable."""
    import rasterio

    area = gpd.GeoDataFrame(geometry=[zip_.buffer(margin_m)], crs=aoi_gdf.crs)
    tif = path.with_suffix(".tif")
    try:
        fetch_ortho(area, tif, resolution=0.5)
        with rasterio.open(tif) as src:
            img = src.read([1, 2, 3]).transpose(1, 2, 0)
            left, bottom, right, top = src.bounds
    except Exception as exc:  # noqa: BLE001 — the figure is optional
        logger.warning("Orthophoto unavailable (%s)", exc)
        return False
    finally:
        tif.unlink(missing_ok=True)
    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    ax.imshow(img, extent=(left, right, bottom, top))
    gpd.GeoSeries([zip_]).plot(ax=ax, facecolor="none", edgecolor="#ff2d2d", linewidth=2)
    ax.plot([left + 20, left + 120], [bottom + 25, bottom + 25], color="white", lw=3)
    ax.text(left + 70, bottom + 38, "100 m", color="white", ha="center", fontsize=8)
    ax.text(
        right - 10, bottom + 10, "© IGN, orthophotographie", color="white", ha="right", fontsize=6
    )
    ax.set_axis_off()
    fig.savefig(path, dpi=150, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return True


def interactive_map(
    zip_, zer, zee, reservoirs: gpd.GeoDataFrame, occ: gpd.GeoDataFrame, path: Path
):
    """Folium map: base layers, rings, protected areas, clustered observations with popups."""
    import folium
    from folium.plugins import MarkerCluster

    def wgs(geom):
        return gpd.GeoSeries([geom], crs=occ.crs).to_crs(4326)

    c = wgs(zip_.centroid).iloc[0]
    m = folium.Map([c.y, c.x], zoom_start=13, tiles=None)
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri WorldImagery",
        name="Satellite (Esri)",
    ).add_to(m)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron").add_to(m)
    rings = [
        ("ZEE", zee, dict(color="#1f78ff", weight=2, dash_array="8 6", fill=False)),
        ("ZER", zer, dict(color="#ff8c00", weight=2, dash_array="8 6", fill=False)),
        ("Emprise", zip_, dict(color="#8b0000", weight=3, fill=True, fillOpacity=0.15)),
    ]
    for name, geom, style in rings:
        folium.GeoJson(
            wgs(geom).__geo_interface__, name=name, style_function=lambda _, s=style: s
        ).add_to(m)
    for kind in reservoirs.kind.unique():
        sub = reservoirs[reservoirs.kind == kind]
        col = LAYER_COLORS.get(kind, "#888888")
        group = folium.FeatureGroup(name=f"Zonage : {sub['type'].iloc[0]}")
        for z in sub.itertuples():
            poly = folium.GeoJson(
                wgs(z.geometry).__geo_interface__,
                style_function=lambda _, c=col: dict(
                    color=c, weight=1.5, fillColor=c, fillOpacity=0.2
                ),
                tooltip=f"{z.type} : {z.nom}",
            )
            poly.add_child(
                folium.Popup(
                    f"<b>{z.type}</b><br>{z.nom}<br>"
                    f"<a href='{z.url}' target='_blank'>Fiche INPN</a>",
                    max_width=300,
                )
            )
            poly.add_to(group)
        group.add_to(m)
    icon = {"Fort": "red", "Modéré": "orange", "Faible": "green"}
    o = occ.to_crs(4326)
    for level in ["Fort", "Modéré", "Faible"]:
        sub = o[o.enjeu == level]
        if level == "Faible":  # keep the file light: only the low-stake records of ZIP/ZER
            sub = sub[sub.zone.isin(["ZIP", "ZER"])]
        cluster = MarkerCluster(name=f"Occurrences : enjeu {level}", show=level != "Faible").add_to(
            m
        )
        for r in sub.itertuples():
            prec = (
                "inconnue" if r.precision_inconnue else f"{int(r.coordinateUncertaintyInMeters)} m"
            )
            html = (
                f"<b><i>{r.species}</i></b><br>{r.nom_commun or '-'}<br>"
                f"Date : {str(r.eventDate)[:10]}"
                f"{' (historique)' if r.donnee_historique else ''}<br>Source : {r.source}<br>"
                f"Protection : {'oui' if r.protege_fr else 'non'} ; "
                f"directive : {r.directive or '-'} ; "
                f"UICN : {r.uicn}<br>Précision : {prec}<br>Zone : {r.zone}, enjeu <b>{level}</b>"
            )
            marker = folium.Marker(
                [r.geometry.y, r.geometry.x], popup=folium.Popup(html, max_width=320)
            )
            marker.add_child(folium.Icon(color=icon[level], icon="leaf"))
            marker.add_to(cluster)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(str(path))
