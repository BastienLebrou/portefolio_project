"""Static report maps: clean IGN base map, scale bar and north arrow on every map.

Four maps: situation (ZEE), proximity (ZER, orthophoto), habitats (ZER, plan), Natura 2000.
One symbology everywhere: parcels in red, ZER dashed orange, ZEE dashed blue, motorway dark grey,
watercourses blue, protected areas by type.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import requests  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from PIL import Image  # noqa: E402
from shapely.geometry.base import BaseGeometry  # noqa: E402
from shapely.ops import nearest_points  # noqa: E402

logger = logging.getLogger("biodiag")

WMS = "https://data.geopf.fr/wms-r/wms"
ORTHO, PLAN = "ORTHOIMAGERY.ORTHOPHOTOS", "GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
RED, ORANGE, BLUE, GREY = "#C0392B", "#E67E22", "#1F78FF", "#3B3B3B"
KIND_COLORS = {
    "znieff1": "#8E44AD", "znieff2": "#2980B9", "natura2000_zps": "#27AE60",
    "natura2000_sic": "#16A085", "apb": "#C0392B", "rnn": "#D35400", "rnr": "#D35400",
    "pn": "#16A085", "pnr": "#7F8C8D",
}  # fmt: skip
HABITAT_COLORS = {
    "Vigne": "#9B59B6", "Forêt fermée de conifères": "#1E6B3A", "Forêt fermée de feuillus": "#58A55C",
    "Forêt fermée mixte": "#3E8E4E", "Forêt ouverte": "#A9D18E", "Bois": "#7FB77E", "Haie": "#2E4F2F",
    "Verger": "#F5B041", "Lande ligneuse": "#C9A66B",
}  # fmt: skip
STAKE_COLORS = {"Faible": "#2E9E44", "Modéré": "#F39C12", "Fort": "#D62728"}


def _square_bbox(geom: BaseGeometry, margin: float) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = geom.buffer(margin).bounds
    cx, cy, h = (minx + maxx) / 2, (miny + maxy) / 2, max(maxx - minx, maxy - miny) / 2
    return cx - h, cy - h, cx + h, cy + h


def _basemap(ax, bbox, layer: str, px: int = 1400) -> bool:
    """Draw an IGN WMS layer under the map (Lambert-93 bbox). False if the service fails."""
    params: dict[str, str | int] = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap", "STYLES": "", "LAYERS": layer,
        "CRS": "EPSG:2154", "BBOX": ",".join(f"{v:.1f}" for v in bbox), "WIDTH": px, "HEIGHT": px,
        "FORMAT": "image/jpeg" if layer == ORTHO else "image/png",
    }  # fmt: skip
    try:
        r = requests.get(WMS, params=params, timeout=90)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as exc:  # noqa: BLE001 - maps degrade to a blank base, never stop the report
        logger.warning("Base map %s unavailable (%s)", layer, exc)
        return False
    ax.imshow(img, extent=(bbox[0], bbox[2], bbox[1], bbox[3]), zorder=0)
    return True


def _decor(ax, bbox, title: str, credit: str) -> None:
    """Frame, north arrow, scale bar and credit."""
    minx, miny, maxx, maxy = bbox
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_edgecolor("#222222")
        s.set_linewidth(1.0)
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left", color="#222222")
    # north arrow (top right)
    ax.annotate("", xy=(0.93, 0.95), xytext=(0.93, 0.85), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color="#111111", lw=1.6), zorder=20)  # fmt: skip
    ax.text(0.93, 0.965, "N", transform=ax.transAxes, ha="center", va="bottom", fontsize=11,
            fontweight="bold", zorder=20,
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.8))  # fmt: skip
    # scale bar (bottom left): a "nice" length of about a fifth of the width
    width = maxx - minx
    nice = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
    length = min(nice, key=lambda v: abs(v - width / 5))
    x0, y0 = minx + width * 0.04, miny + width * 0.05
    ax.add_patch(plt.Rectangle((x0 - width * 0.01, y0 - width * 0.025), length + width * 0.06,
                               width * 0.075, fc="white", ec="none", alpha=0.85, zorder=19))  # fmt: skip
    for i in range(4):
        ax.add_patch(plt.Rectangle((x0 + i * length / 4, y0), length / 4, width * 0.008,
                                   fc="black" if i % 2 == 0 else "white", ec="black", lw=0.6, zorder=20))  # fmt: skip
    label = f"{length} m" if length < 1000 else f"{length // 1000} km"
    ax.text(x0, y0 + width * 0.014, "0", fontsize=7, zorder=20)
    ax.text(x0 + length, y0 + width * 0.014, label, fontsize=7, ha="center", zorder=20)
    ax.text(maxx - width * 0.01, miny + width * 0.008, credit, fontsize=5.5, ha="right",
            color="white" if "orthophoto" in credit else "#333333", zorder=20)  # fmt: skip


def _save(fig, path: Path) -> None:
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _plot(gdf, ax, **kw) -> None:
    if gdf is not None and len(gdf):
        gdf.plot(ax=ax, **kw)


def map_proximity(zip_, zer, occ: gpd.GeoDataFrame, env: dict, path: Path) -> None:
    """Close-range map: orthophoto, parcels, 500 m / 1 km rings, motorway, water, patrimonial records."""
    bbox = _square_bbox(zip_, 1150)
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ok = _basemap(ax, bbox, ORTHO)
    for r, ls in [(500, ":"), (1000, "--")]:
        gpd.GeoSeries([zip_.buffer(r)]).plot(ax=ax, facecolor="none", edgecolor=ORANGE if r == 1000 else "white",
                                             linestyle=ls, linewidth=1.6, zorder=3)  # fmt: skip
    if env.get("autoroute") is not None:
        gpd.GeoSeries([env["autoroute"]]).plot(ax=ax, color="#F4D03F", linewidth=2.2, zorder=4)
    _plot(env.get("cours_eau"), ax, color="#00BFFF", linewidth=1.6, zorder=4)
    _plot(env.get("hydro"), ax, color="#00BFFF", alpha=0.6, edgecolor="#0099CC", zorder=4)
    gpd.GeoSeries([zip_]).plot(
        ax=ax, facecolor=RED, alpha=0.30, edgecolor=RED, linewidth=2.4, zorder=6
    )
    pat = occ[occ.patrimoniale & (occ.dist_m <= 1150)]
    marks = {"Oiseaux": "^", "Amphibiens": "s", "Reptiles": "D", "Insectes": "P", "Mammifères": "o"}
    for g, sub in pat.groupby("groupe"):
        ax.scatter(sub.geometry.x, sub.geometry.y, marker=marks.get(g, "o"), s=46, c="#FFFFFF",
                   edgecolors="#111111", linewidths=1.0, zorder=7)  # fmt: skip
    leg = [Patch(fc=RED, alpha=0.4, ec=RED, label="Parcelles du projet"),
           Line2D([], [], color="#BBBBBB", ls=":", lw=1.6, label="Rayon 500 m"),
           Line2D([], [], color=ORANGE, ls="--", lw=1.6, label="Rayon 1 km (ZER)"),
           Line2D([], [], color="#F4D03F", lw=2.2, label="Autoroute A9"),
           Line2D([], [], color="#00BFFF", lw=2, label="Cours d'eau et bassins")]  # fmt: skip
    leg += [Line2D([], [], marker=marks.get(g, "o"), ls="", mfc="white", mec="#111111", ms=6,
                   label=f"Espèce patrimoniale : {g.lower()}") for g in sorted(pat.groupby("groupe").groups)]  # fmt: skip
    _decor(
        ax,
        bbox,
        "Carte de proximité : la zone d'étude rapprochée",
        "© IGN, orthophotographie" if ok else "",
    )
    ax.legend(
        handles=leg,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=2,
        fontsize=7,
        frameon=False,
    )
    _save(fig, path)


def map_habitats(zip_, zer, reservoirs: gpd.GeoDataFrame, env: dict, path: Path) -> None:
    """Land-cover map of the ZER (BD TOPO vegetation) on the IGN plan, with ZNIEFF I outline."""
    bbox = _square_bbox(zip_, 1150)
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ok = _basemap(ax, bbox, PLAN)
    veg = env.get("veg_all")
    handles: list = []
    if veg is not None and len(veg):
        for nature, sub in veg.groupby("nature"):
            col = HABITAT_COLORS.get(nature, "#B0B0B0")
            sub.plot(ax=ax, color=col, alpha=0.55, edgecolor=col, linewidth=0.4, zorder=2)
            handles.append(Patch(fc=col, alpha=0.7, label=nature))
    z1 = reservoirs[reservoirs.kind == "znieff1"]
    if len(z1):
        z1.boundary.plot(
            ax=ax, color=KIND_COLORS["znieff1"], linewidth=2.2, linestyle="-.", zorder=5
        )
        handles.append(
            Line2D([], [], color=KIND_COLORS["znieff1"], ls="-.", lw=2, label="ZNIEFF type I")
        )
    _plot(env.get("cours_eau"), ax, color="#1F78FF", linewidth=1.4, zorder=4)
    if env.get("autoroute") is not None:
        gpd.GeoSeries([env["autoroute"]]).plot(ax=ax, color=GREY, linewidth=2.4, zorder=4)
        handles.append(Line2D([], [], color=GREY, lw=2.4, label="Autoroute A9"))
    handles.append(Line2D([], [], color="#1F78FF", lw=1.6, label="Cours d'eau"))
    gpd.GeoSeries([zip_]).plot(
        ax=ax, facecolor=RED, alpha=0.35, edgecolor=RED, linewidth=2.4, zorder=6
    )
    handles.insert(0, Patch(fc=RED, alpha=0.45, ec=RED, label="Parcelles du projet"))
    gpd.GeoSeries([zer]).boundary.plot(ax=ax, color=ORANGE, linestyle="--", linewidth=1.6, zorder=6)
    handles.append(Line2D([], [], color=ORANGE, ls="--", lw=1.6, label="Rayon 1 km (ZER)"))
    _decor(
        ax,
        bbox,
        "Carte des milieux : occupation du sol de la zone rapprochée",
        "© IGN, Plan IGN, BD TOPO" if ok else "",
    )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=3,
        fontsize=7,
        frameon=False,
    )
    _save(fig, path)


def map_natura(zip_, reservoirs: gpd.GeoDataFrame, path: Path, radius_m: float = 5500) -> None:
    """Natura 2000 sites around the parcels with the shortest distance to each."""
    bbox = _square_bbox(zip_, radius_m)
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ok = _basemap(ax, bbox, PLAN)
    handles: list = [Patch(fc=RED, alpha=0.5, ec=RED, label="Parcelles du projet")]
    n2k = reservoirs[reservoirs.kind.isin(["natura2000_zps", "natura2000_sic"])]
    for kind, sub in n2k.groupby("kind"):
        col = KIND_COLORS[kind]
        sub.plot(ax=ax, facecolor=col, alpha=0.28, edgecolor=col, linewidth=1.8, zorder=2)
        handles.append(Patch(fc=col, alpha=0.5, ec=col, label=sub["type"].iloc[0]))
        for r in sub.itertuples():
            a, b = nearest_points(zip_, r.geometry)
            if not (bbox[0] < b.x < bbox[2] and bbox[1] < b.y < bbox[3]):
                continue
            ax.plot([a.x, b.x], [a.y, b.y], color=col, lw=1.2, ls="--", zorder=5)
            d = zip_.distance(r.geometry) / 1000
            ax.text((a.x + b.x) / 2, (a.y + b.y) / 2, f"{d:.2f} km".replace(".", ","), fontsize=8, fontweight="bold",
                    color=col, ha="center", zorder=8,
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=col, lw=0.8))  # fmt: skip
    z1 = reservoirs[reservoirs.kind == "znieff1"]
    if len(z1):
        z1.boundary.plot(
            ax=ax, color=KIND_COLORS["znieff1"], linewidth=1.4, linestyle="-.", zorder=3
        )
        handles.append(
            Line2D([], [], color=KIND_COLORS["znieff1"], ls="-.", lw=1.6, label="ZNIEFF type I")
        )
    c = zip_.centroid
    ax.scatter([c.x], [c.y], marker="*", s=220, c=RED, edgecolors="white", linewidths=1.2, zorder=9)
    for rr in (2000, 4000):
        gpd.GeoSeries([zip_.buffer(rr)]).boundary.plot(
            ax=ax, color="#555555", linewidth=0.7, linestyle=":", zorder=4
        )
        ax.text(
            c.x,
            c.y + rr,
            f"{rr // 1000} km",
            fontsize=6.5,
            ha="center",
            va="bottom",
            color="#333333",
            zorder=6,
        )
    _decor(
        ax,
        bbox,
        "Carte des sites Natura 2000 autour du projet",
        "© IGN, Plan IGN, INPN" if ok else "",
    )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=2,
        fontsize=7,
        frameon=False,
    )
    _save(fig, path)


def map_situation(
    zip_, zer, zee, reservoirs: gpd.GeoDataFrame, occ: gpd.GeoDataFrame, path: Path
) -> None:
    """Wide map: ZER/ZEE rings, ZNIEFF, observations by stake level, on the IGN plan."""
    bbox = _square_bbox(zee, 300)
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ok = _basemap(ax, bbox, PLAN)
    handles: list = []
    for kind in ["znieff2", "znieff1"]:
        sub = reservoirs[reservoirs.kind == kind]
        if len(sub):
            col = KIND_COLORS[kind]
            sub.plot(ax=ax, facecolor=col, alpha=0.15, edgecolor=col, linewidth=1.0, zorder=2)
            handles.append(Patch(fc=col, alpha=0.4, ec=col, label=sub["type"].iloc[0]))
    for geom, col, lab in [(zee, BLUE, "Rayon 5 km (ZEE)"), (zer, ORANGE, "Rayon 1 km (ZER)")]:
        gpd.GeoSeries([geom]).boundary.plot(
            ax=ax, color=col, linestyle="--", linewidth=1.6, zorder=4
        )
        handles.append(Line2D([], [], color=col, ls="--", lw=1.6, label=lab))
    for level in ["Faible", "Modéré", "Fort"]:
        d = occ[occ.enjeu == level]
        ax.scatter(d.geometry.x, d.geometry.y, s=3 if level == "Faible" else 7, c=STAKE_COLORS[level],
                   alpha=0.4 if level == "Faible" else 0.85, linewidths=0, zorder=5)  # fmt: skip
        handles.append(
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                color=STAKE_COLORS[level],
                ms=5,
                label=f"Observation, enjeu {level.lower()}",
            )
        )
    gpd.GeoSeries([zip_]).plot(ax=ax, color=RED, edgecolor=RED, linewidth=3, zorder=7)
    handles.insert(0, Patch(fc=RED, ec=RED, label="Parcelles du projet"))
    _decor(
        ax,
        bbox,
        "Carte de situation : la zone d'étude éloignée",
        "© IGN, Plan IGN, INPN, GBIF" if ok else "",
    )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=3,
        fontsize=7,
        frameon=False,
    )
    _save(fig, path)


def map_bias(zip_, occ: gpd.GeoDataFrame, env: dict, bias: dict, path: Path) -> None:
    """Where the observations are: road and rest areas, the most active observer, the parcels."""
    bbox = _square_bbox(zip_, 900)
    fig, ax = plt.subplots(figsize=(6.6, 6.6))
    ok = _basemap(ax, bbox, ORTHO)
    area = []
    if env.get("autoroute") is not None:
        area.append(env["autoroute"].buffer(150))
    if len(env.get("aires", [])):
        area.append(env["aires"].union_all().buffer(150))
    if area:
        gpd.GeoSeries([g for g in area]).plot(
            ax=ax, color="#F4D03F", alpha=0.25, edgecolor="none", zorder=2
        )
    if env.get("autoroute") is not None:
        gpd.GeoSeries([env["autoroute"]]).plot(ax=ax, color="#F4D03F", linewidth=2.0, zorder=3)
    _plot(env.get("aires"), ax, facecolor="#00BFFF", alpha=0.55, edgecolor="#0080B0", zorder=4)
    near = occ[occ.dist_m <= 900]
    top = near.loc[near.index.intersection(bias["top_idx"])]
    others = near.drop(top.index)
    ax.scatter(
        others.geometry.x,
        others.geometry.y,
        s=14,
        c="white",
        edgecolors="#222222",
        linewidths=0.5,
        zorder=6,
    )
    ax.scatter(
        top.geometry.x,
        top.geometry.y,
        s=34,
        marker="D",
        c="#FF8C00",
        edgecolors="#222222",
        linewidths=0.6,
        zorder=7,
    )
    gpd.GeoSeries([zip_]).plot(
        ax=ax, facecolor=RED, alpha=0.35, edgecolor=RED, linewidth=2.4, zorder=8
    )
    handles = [
        Patch(fc=RED, alpha=0.45, ec=RED, label="Parcelles du projet (0 observation)"),
        Line2D([], [], color="#F4D03F", lw=2.2, label="Autoroute A9"),
        Patch(fc="#F4D03F", alpha=0.35, label="Moins de 150 m de l'A9 ou d'une aire"),
        Patch(fc="#00BFFF", alpha=0.6, ec="#0080B0", label="Aire de repos"),
        Line2D(
            [],
            [],
            marker="D",
            ls="",
            mfc="#FF8C00",
            mec="#222222",
            ms=6,
            label="Observateur le plus actif",
        ),
        Line2D(
            [], [], marker="o", ls="", mfc="white", mec="#222222", ms=5, label="Autres observations"
        ),
    ]
    _decor(
        ax,
        bbox,
        "Carte du biais d'observation autour des parcelles",
        "© IGN, orthophotographie, GBIF" if ok else "",
    )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=2,
        fontsize=7,
        frameon=False,
    )
    _save(fig, path)
