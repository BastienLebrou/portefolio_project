"""Protected areas, watercourses, hedges / woods, neighbouring PV parks, farmland declarations.

All layers come from the Géoplateforme WFS through :func:`core.sources.fetch_bdtopo` (the one
paginated, AOI-clipped WFS reader of ScruTech). Every fetch degrades to an empty result with a
warning: a missing layer must not stop the diagnostic.
"""

from __future__ import annotations

import io
import logging
import re
import time

import geopandas as gpd
import pandas as pd
import requests
from core.constants import L93
from core.sources import VEGETATION_TYPENAME, WFS_URL, fetch_bdtopo
from shapely.geometry.base import BaseGeometry

logger = logging.getLogger("biodiag")

# kind -> (WFS typename, label). ``znieff1`` / ``natura2000_*`` also drive the "Fort" stakes.
PROTECTED_LAYERS = {
    "znieff1": ("patrinat_znieff1:znieff1", "ZNIEFF I"),
    "znieff2": ("patrinat_znieff2:znieff2", "ZNIEFF II"),
    "natura2000_zps": ("patrinat_zps:zps", "Natura 2000 ZPS"),
    "natura2000_sic": ("patrinat_sic:sic", "Natura 2000 ZSC/SIC"),
    "apb": ("patrinat_apb:apb", "APPB"),
    "rnn": ("patrinat_rnn:rnn", "Réserve naturelle nationale"),
    "rnr": ("patrinat_rnr:rnr", "Réserve naturelle régionale"),
    "pn": ("patrinat_pn2:pn", "Parc national"),
    "pnr": ("patrinat_pnr:pnr", "Parc naturel régional"),
}
WATERCOURSES = "BDTOPO_V3:cours_d_eau"
HYDRO_SURFACES = "BDTOPO_V3:surface_hydrographique"
ROADS = "BDTOPO_V3:troncon_de_route"
TRANSPORT_EQUIPMENT = "BDTOPO_V3:equipement_de_transport"
RPG_LATEST = "RPG.LATEST:parcelles_graphiques"
COMMUNES = "BDTOPO_V3:commune"
OVERPASS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
# IGN dataset of known PV parks; the typename embeds the dataset date, update it if it 404s.
PV_PARKS = "igngpf_4902_20260309_tables_sans_tirets:parcs_photovoltaiques"
RPG_LABELS = {
    "PPH": "prairie permanente",
    "PTR": "prairie temporaire",
    "VRC": "vigne",
    "VRT": "vigne",
    "BTH": "blé tendre",
    "BDH": "blé dur",
    "ORH": "orge d'hiver",
    "ORP": "orge de printemps",
    "MIS": "maïs",
    "TOU": "tournesol",
    "SPH": "prairie/pâturage",
    "SPL": "surface pastorale",
    "J6S": "jachère",
    "J5M": "jachère",
    "OLI": "oliveraie",
    "VRG": "verger",
}


def _fetch_unpaged(typename: str, keep: list[str], area: BaseGeometry) -> gpd.GeoDataFrame:
    """One un-paged WFS request: for small layers whose server rejects STARTINDEX paging."""
    minx, miny, maxx, maxy = area.bounds
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": typename,
        "SRSNAME": L93,
        "BBOX": f"{minx:.0f},{miny:.0f},{maxx:.0f},{maxy:.0f},{L93}",
        "COUNT": "3000",
        "OUTPUTFORMAT": "application/json",
    }
    try:
        r = requests.get(WFS_URL, params=params, timeout=60)
        r.raise_for_status()
        g = gpd.read_file(io.BytesIO(r.content)).set_crs(L93, allow_override=True)
    except Exception as exc:  # noqa: BLE001 - the layer is optional
        logger.warning("WFS %s unavailable (%s)", typename, exc)
        return gpd.GeoDataFrame({c: [] for c in keep}, geometry=[], crs=L93)
    return g[g.intersects(area)][[*[c for c in keep if c in g.columns], "geometry"]].copy()


def _fetch(
    typename: str, keep: list[str], area: BaseGeometry, *, required: bool = False, tries: int = 4
) -> gpd.GeoDataFrame:
    """One WFS layer in the AOI, retried. An optional layer degrades to empty; a required one stops.

    A protected-area layer that silently came back empty would make the report say "no ZNIEFF
    nearby", which is a wrong conclusion, so those layers are required.
    """
    last: Exception | None = None
    for i in range(tries):
        try:
            return fetch_bdtopo(gpd.GeoDataFrame(geometry=[area], crs=L93), typename, keep)
        except Exception as exc:  # noqa: BLE001 - network or server hiccup, retried below
            last = exc
            logger.warning("WFS %s failed (%s), try %d/%d", typename, exc, i + 1, tries)
            time.sleep(5 * (i + 1))
    if required:
        raise RuntimeError(f"WFS layer {typename} unavailable after {tries} tries: {last}")
    return gpd.GeoDataFrame({c: [] for c in keep}, geometry=[], crs=L93)


def fetch_protected_areas(area: BaseGeometry) -> gpd.GeoDataFrame:
    """Protected / inventoried areas touching ``area`` (L93). Columns: kind, type, nom, url."""
    frames = []
    for kind, (typename, label) in PROTECTED_LAYERS.items():
        g = _fetch(typename, ["nom_site", "url_fiche"], area, required=True)
        if g.empty:
            continue
        frames.append(
            gpd.GeoDataFrame(
                {
                    "kind": kind,
                    "type": label,
                    "nom": g.nom_site,
                    "url": g.get("url_fiche", ""),
                    "geometry": g.geometry,
                },
                crs=L93,
            )
        )
    if not frames:
        return gpd.GeoDataFrame(
            {"kind": [], "type": [], "nom": [], "url": []}, geometry=[], crs=L93
        )
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=L93)


def fetch_environment(zip_: BaseGeometry, zer: BaseGeometry, zee: BaseGeometry) -> dict:
    """Nearest watercourse, vegetation features in ZER (vineyards excluded), PV parks in ZEE."""
    env: dict = {
        "eau": None, "veg": pd.DataFrame(), "pv": pd.DataFrame(), "veg_all": gpd.GeoDataFrame(),
        "wind": pd.DataFrame(), "cours_eau": gpd.GeoDataFrame(), "hydro": gpd.GeoDataFrame(),
        "autoroute": None, "autoroute_dist": None,
        "routes": gpd.GeoDataFrame(), "aires": gpd.GeoDataFrame(),
    }  # fmt: skip
    water = _fetch(WATERCOURSES, ["toponyme"], zee)
    if not water.empty:
        water["d"] = water.distance(zip_)
        env["cours_eau"] = water
        w = water.sort_values("d").iloc[0]
        env["eau"] = (w.get("toponyme") or "cours d'eau non nommé", float(w.d))
    roads = _fetch(ROADS, ["nature", "numero"], zee)
    if not roads.empty:
        env["routes"] = roads
        motorway = roads[roads.nature == "Type autoroutier"]
        if not motorway.empty:
            env["autoroute"] = motorway.union_all()
            env["autoroute_dist"] = float(zip_.distance(env["autoroute"]))
    equip = _fetch(TRANSPORT_EQUIPMENT, ["nature", "toponyme"], zer.buffer(500))
    if not equip.empty:
        aires = equip[equip.nature.str.contains("Aire", na=False)].copy()
        aires["d"] = aires.distance(zip_)
        env["aires"] = aires.sort_values("d")
    hydro = _fetch(HYDRO_SURFACES, ["nature", "persistance", "origine"], zer.buffer(500))
    if not hydro.empty:
        hydro["d"] = hydro.distance(zip_)
        env["hydro"] = hydro.sort_values("d")
    veg = _fetch(VEGETATION_TYPENAME, ["nature"], zer)
    env["veg_all"] = veg
    if not veg.empty:
        veg = veg[veg.nature != "Vigne"].copy()
        veg["d"] = veg.distance(zip_)
        veg["ha"] = veg.intersection(zer).area / 1e4
        env["veg"] = (
            veg.groupby("nature")
            .agg(n=("d", "size"), ha=("ha", "sum"), d=("d", "min"))
            .reset_index()
            .sort_values("d")
        )
    pv = _fetch_unpaged(PV_PARKS, ["nom_com", "millesime", "surf_parc"], zee)
    if not pv.empty:
        pv["d"] = pv.distance(zip_)
        pv["commune"] = pv.nom_com.astype(str).str.strip("{}")
        env["pv"] = pv.sort_values("d")
    env["wind"] = fetch_wind(zip_, zee)
    return env


def fetch_wind(zip_: BaseGeometry, zee: BaseGeometry) -> pd.DataFrame:
    """Wind turbines of OpenStreetMap in the ZEE, one row per commune and year (n, distance in m).

    OSM is crowd-sourced: years are the ``start_date`` tags and may be missing ("n.c."). The query
    is required: an empty answer by failure would read as "no wind park nearby".
    """
    s, w, n, east = gpd.GeoSeries([zee], crs=L93).to_crs(4326).total_bounds[[1, 0, 3, 2]]
    box = f"{s:.5f},{w:.5f},{n:.5f},{east:.5f}"
    sel = f'["generator:source"="wind"]({box})'
    q = f"[out:json][timeout:60];(node{sel};way{sel};);out center tags;"
    last: Exception | None = None
    for i in range(4):
        try:
            r = requests.post(
                OVERPASS[i % len(OVERPASS)],
                data={"data": q},
                timeout=90,
                headers={"User-Agent": "scrutech-biodiag/0.1"},
            )
            r.raise_for_status()
            items = r.json()["elements"]
            break
        except Exception as exc:  # noqa: BLE001 - network hiccup, retried
            last = exc
            logger.warning("Overpass failed (%s), try %d/4", exc, i + 1)
            time.sleep(10 * (i + 1))
    else:
        raise RuntimeError(f"OpenStreetMap wind turbines unavailable: {last}")
    pts = [
        (e.get("lon", e.get("center", {}).get("lon")), e.get("lat", e.get("center", {}).get("lat")))
        for e in items
    ]
    years = [(e.get("tags", {}).get("start_date") or "")[:4] for e in items]
    if not pts:
        return pd.DataFrame(columns=["commune", "annee", "n", "d"])
    g = gpd.GeoDataFrame(
        {"annee": [y if re.fullmatch(r"\d{4}", y) else "" for y in years]},
        geometry=gpd.points_from_xy([p[0] for p in pts], [p[1] for p in pts]),
        crs=4326,
    ).to_crs(L93)
    g = g[g.intersects(zee)].copy()
    if g.empty:
        return pd.DataFrame(columns=["commune", "annee", "n", "d"])
    g["d"] = g.distance(zip_)
    com = _fetch(COMMUNES, ["nom_officiel"], zee)
    g["commune"] = "n.c."
    if not com.empty:
        j = gpd.sjoin_nearest(g[["geometry"]], com[["nom_officiel", "geometry"]], how="left")
        g["commune"] = j.nom_officiel.groupby(level=0).first().reindex(g.index).fillna("n.c.")
    rows = [
        {"commune": com_, "annee": yr or "n.c.", "n": len(p), "d": float(p.d.min())}
        for (com_, yr), p in g.groupby(["commune", "annee"])
    ]
    return pd.DataFrame(rows).sort_values("d").reset_index(drop=True)


def farmland_declared(zip_: BaseGeometry) -> list[str]:
    """Crops declared to the RPG on the footprint ([] = not declared: fallow or uncultivated)."""
    rpg = _fetch(RPG_LATEST, ["code_cultu"], zip_)
    return (
        sorted({f"{RPG_LABELS.get(c, c)} ({c})" for c in rpg.code_cultu}) if not rpg.empty else []
    )
