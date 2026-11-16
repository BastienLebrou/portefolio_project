"""Proximity analysis: species per distance band, flora, motorway context, habitats, wetlands.

Pure pandas / geopandas on data already downloaded, so it is unit-testable offline. "Band" = distance
from the footprint (ZIP) to the observation.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

BAND_EDGES = [-1.0, 0.5, 500.0, 1000.0, 2000.0, 5000.1]
BAND_LABELS = ["Parcelles", "0 à 500 m", "500 m à 1 km", "1 à 2 km", "2 à 5 km"]


def add_bands(occ: gpd.GeoDataFrame, zip_: BaseGeometry) -> gpd.GeoDataFrame:
    """Add ``dist_m`` and ``bande`` (distance band to the footprint) to the observations."""
    out = occ.copy()
    out["dist_m"] = out.distance(zip_)
    out["bande"] = pd.cut(out.dist_m, BAND_EDGES, labels=BAND_LABELS)
    return out


def species_by_band(occ: pd.DataFrame) -> pd.DataFrame:
    """Distinct species and observations per group and distance band (exact counts)."""
    sp = occ.groupby(["groupe", "bande"], observed=False).species.nunique().unstack(fill_value=0)
    obs = occ.groupby(["groupe", "bande"], observed=False).size().unstack(fill_value=0)
    sp.loc["Toutes espèces"] = occ.groupby("bande", observed=False).species.nunique()
    obs.loc["Toutes espèces"] = occ.groupby("bande", observed=False).size()
    return sp.reindex(columns=BAND_LABELS, fill_value=0), obs.reindex(
        columns=BAND_LABELS, fill_value=0
    )


def patrimonial_by_band(occ: pd.DataFrame) -> pd.DataFrame:
    """Patrimonial species: observations per band, total, nearest distance, last year."""
    pat = occ[occ.patrimoniale]
    tab = pat.groupby(["species", "bande"], observed=False).size().unstack(fill_value=0)
    tab = tab.reindex(columns=BAND_LABELS, fill_value=0)
    tab["Total"] = tab.sum(axis=1)
    tab["Distance min. (m)"] = pat.groupby("species").dist_m.min().round(0).astype(int)
    tab["Dernière année"] = pat.groupby("species").year.max().astype("Int64")
    return tab.sort_values(["Distance min. (m)", "Total"], ascending=[True, False])


def flora_summary(occ: pd.DataFrame) -> dict:
    """Flora records per band, protected or patrimonial flora, inventory pressure."""
    fl = occ[occ.groupe.str.startswith("Flore")]
    near = fl[fl.dist_m <= 1000]
    return {
        "n_obs_zee": len(fl), "n_sp_zee": fl.species.nunique(),
        "n_obs_zer": len(near), "n_sp_zer": near.species.nunique(),
        "n_obs_parcelles": int((fl.dist_m <= 0.5).sum()),
        "protegee_zer": sorted(near[near.protege_fr].species.unique()),
        "patrimoniale_zer": sorted(near[near.patrimoniale].species.unique()),
        "patrimoniale_zee": sorted(fl[fl.patrimoniale].species.unique()),
        "dist_patri_min": {s: int(d.dist_m.min()) for s, d in fl[fl.patrimoniale].groupby("species")},
    }  # fmt: skip


RINGS = [(0, 150), (150, 500), (500, 1000), (1000, 2000), (2000, 6000)]


def density_by_motorway_distance(
    occ: gpd.GeoDataFrame, motorway: BaseGeometry, zee
) -> pd.DataFrame:
    """Observations per km² by distance ring from the motorway, inside the ZEE.

    Tests whether the motorway biases the observation effort (access, noise, fewer observers).
    """
    d = occ.distance(motorway)
    rows = []
    for a, b in RINGS:
        ring = motorway.buffer(b).difference(motorway.buffer(a)).intersection(zee)
        km2 = ring.area / 1e6
        n = int(((d >= a) & (d < b)).sum())
        label = f"{a} à {b} m" if b < 6000 else "plus de 2 km"
        rows.append([label, n, round(km2, 2), round(n / km2) if km2 > 0 else np.nan])
    return pd.DataFrame(
        rows, columns=["Distance à l'autoroute", "Observations", "Surface km²", "Obs. par km²"]
    )


def habitats_table(zer, veg: gpd.GeoDataFrame, reservoirs: gpd.GeoDataFrame, zip_) -> pd.DataFrame:
    """Land-cover classes of the ZER (BD TOPO vegetation) with area, share and nearest distance."""
    if veg.empty:
        return pd.DataFrame()
    v = veg.copy()
    v["ha"] = v.intersection(zer).area / 1e4
    v["d"] = v.distance(zip_)
    g = v.groupby("nature").agg(ha=("ha", "sum"), d=("d", "min")).reset_index()
    g["part"] = g.ha / (zer.area / 1e4) * 100
    g = g.sort_values("ha", ascending=False)
    out = pd.DataFrame({
        "Milieu (BD TOPO)": g.nature, "Surface en ZER (ha)": g.ha.round(1),
        "Part de la ZER": g.part.round(0).astype(int).astype(str) + " %",
        "Distance min. (m)": g.d.round(0).astype(int),
    })  # fmt: skip
    return out


def zonage_cover(zer, reservoirs: gpd.GeoDataFrame, kinds: tuple[str, ...]) -> float:
    """Share (0-1) of the ZER covered by the given protected-area kinds."""
    sub = reservoirs[reservoirs.kind.isin(kinds)]
    return float(zer.intersection(sub.union_all()).area / zer.area) if len(sub) else 0.0


def coarse_summary(coarse: pd.DataFrame) -> pd.DataFrame:
    """Species seen in imprecisely located records (> 1 km), one row per species.

    These records sit at a grid-cell centre: they say a species was recorded in the sector,
    not on the parcels. Used as a sensitivity check on the precise data set.
    """
    if coarse.empty:
        return pd.DataFrame()
    g = coarse.groupby(["species", "groupe"], as_index=False).agg(
        nom_commun=("nom_commun", "first"), n_obs=("key", "count"),
        precision_mediane=("coordinateUncertaintyInMeters", "median"),
        derniere_annee=("year", "max"), uicn=("uicn", "first"), protege=("protege_fr", "max"),
        directive=("directive", "first"), patrimoniale=("patrimoniale", "max"),
        sens=("sens_solaire", "first"),
    )  # fmt: skip
    return g.sort_values(["patrimoniale", "n_obs"], ascending=[False, False]).reset_index(drop=True)


def observer_bias(
    occ: gpd.GeoDataFrame, motorway, aires: gpd.GeoDataFrame, radius: float = 500.0
) -> dict:
    """Human observation bias near the parcels: who observed, when, and how close to the road.

    Uses the precise records within ``radius`` of the parcels. Observer names are never returned
    (GBIF user names are pseudonyms of private people): only counts and dates.
    """
    near = occ[occ.dist_m <= radius].copy()
    ua = aires.union_all() if len(aires) else None
    near["d_road"] = near.distance(motorway) if motorway is not None else float("nan")
    near["d_aire"] = near.distance(ua) if ua is not None else float("nan")
    road = near[["d_road", "d_aire"]].min(axis=1)
    top = near.recordedBy.dropna().value_counts()
    top_name = top.index[0] if len(top) else None
    mine = near[near.recordedBy == top_name] if top_name else near.iloc[0:0]
    rest = near.drop(mine.index)
    wide = occ[occ.dist_m <= 1000]
    wide_rest = wide[wide.recordedBy != top_name] if top_name else wide
    cell = (
        (near.geometry.x // 50).astype(int).astype(str)
        + "_"
        + (near.geometry.y // 50).astype(int).astype(str)
    )
    days = sorted(set(mine.eventDate.astype(str).str[:10])) if len(mine) else []
    return {
        "n_near": len(near), "sp_near": int(near.species.nunique()),
        "n_top": len(mine), "top_days": len(days), "top_year": int(mine.year.mode().iat[0]) if len(mine) else None,
        "top_groups": sorted(set(mine.groupe)) if len(mine) else [],
        "n_2026": int((near.year == near.year.max()).sum()), "year_max": int(near.year.max()),
        "n_150": int((road <= 150).sum()), "n_300": int((road <= 300).sum()),
        "cells": int(cell.nunique()), "cells_possible": int(3.14159 * radius**2 / 2500),
        "sp_without": int(rest.species.nunique()),
        "patri_all": int(wide[wide.patrimoniale].species.nunique()),
        "patri_without": int(wide_rest[wide_rest.patrimoniale].species.nunique()),
        "obs_without": len(rest), "top_idx": list(mine.index), "near_idx": list(near.index),
        "aires": [(r.toponyme, float(r.d)) for r in aires.itertuples()] if len(aires) else [],
    }  # fmt: skip
