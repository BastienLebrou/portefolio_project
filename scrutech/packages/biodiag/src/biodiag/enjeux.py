"""Study zones, per-occurrence stakes, species synthesis and landscape context.

Everything here is pure pandas / geopandas on already-downloaded data (no network), so it is
unit-testable on synthetic points.

Zones around the footprint (ZIP): **ZER** = close study zone (default 1 km), **ZEE** = wide study
zone (default 5 km). Stakes, per occurrence:

- ``enjeu_regl``: the literal rule (any nationally protected or CR/EN/VU species in ZIP/ZER = Fort);
  it flags dozens of common species (tits, sparrows), so it is kept as a column only;
- ``enjeu``: the ranking the report uses. **Fort** = *patrimonial* species (directive annex,
  CR/EN/VU/NT, local list) in ZIP/ZER or inside a ZNIEFF I / Natura 2000 site; **Modéré** =
  patrimonial species further out, or protected common species in ZIP/ZER; else **Faible**.
  Records older than ``RECENT_FROM`` never score Fort.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from biodiag import taxa

ORDER = {"Fort": 0, "Modéré": 1, "Faible": 2}
STRONG_KINDS = ("znieff1", "natura2000_sic", "natura2000_zps")


def make_zones(footprint: BaseGeometry, zer_m: float, zee_m: float):
    """(ZIP, ZER, ZEE) in Lambert-93 from the footprint geometry (L93) and the two buffers."""
    return footprint, footprint.buffer(zer_m), footprint.buffer(zee_m)


def qualify(
    occ: gpd.GeoDataFrame,
    zones: tuple[BaseGeometry, BaseGeometry, BaseGeometry],
    reservoirs: gpd.GeoDataFrame,
    names: dict,
) -> gpd.GeoDataFrame:
    """Add zone, vernacular name, source and stakes to classified occurrences (L93)."""
    zip_, zer, zee = zones
    occ = occ.copy()
    occ["nom_commun"] = occ.speciesKey.map(
        lambda k: names["nom"].get(str(int(k)), "") if pd.notna(k) else ""
    )
    occ["nom_commun"] = np.where(
        occ.nom_commun == "", occ.vernacularName.fillna(""), occ.nom_commun
    )
    occ["nom_commun"] = occ.species.map(taxa.FR_NAMES).fillna(occ.nom_commun)
    occ["source"] = occ.datasetKey.map(names["ds"]).fillna(occ.institutionCode)
    occ["zone"] = np.select(
        [occ.within(zip_), occ.within(zer), occ.within(zee)], ["ZIP", "ZER", "ZEE"], "hors ZEE"
    )
    occ = occ[occ.zone != "hors ZEE"].copy()

    strong = reservoirs[reservoirs.kind.isin(STRONG_KINDS)].geometry
    occ["in_zonage_fort"] = _within_any(occ, strong)
    z2 = reservoirs[reservoirs.kind == "znieff2"].geometry
    occ["pres_znieff2"] = _near_any(occ, z2, 200)

    near = occ.zone.isin(["ZIP", "ZER"])
    recent = ~occ.donnee_historique
    occ["enjeu_regl"] = np.select(
        [
            occ.sensible & recent & (near | occ.in_zonage_fort),
            occ.sensible,
            (occ.uicn == "NT") | occ.pres_znieff2,
        ],
        ["Fort", "Modéré", "Modéré"],
        "Faible",
    )
    patri = occ.patrimoniale
    occ["enjeu"] = np.select(
        [
            patri & recent & (near | occ.in_zonage_fort),
            patri & recent,
            occ.sensible & recent & near,
            (occ.uicn == "NT") | occ.pres_znieff2,
        ],
        ["Fort", "Modéré", "Modéré", "Modéré"],
        "Faible",
    )
    old = occ.donnee_historique
    occ.loc[old, "enjeu"] = np.where(patri[old], "Modéré", "Faible")  # unconfirmed: never Fort
    return occ


def _within_any(pts: gpd.GeoDataFrame, polys: gpd.GeoSeries) -> pd.Series:
    if polys.empty:
        return pd.Series(False, index=pts.index)
    return pts.intersects(polys.union_all())


def _near_any(pts: gpd.GeoDataFrame, polys: gpd.GeoSeries, dist_m: float) -> pd.Series:
    if polys.empty:
        return pd.Series(False, index=pts.index)
    return pts.distance(polys.union_all()) < dist_m


def species_summary(occ: pd.DataFrame) -> pd.DataFrame:
    """One row per species: counts, statuses, worst stake, ordered Fort first."""

    def worst(s: pd.Series) -> str:
        return min(s, key=ORDER.__getitem__)

    s = occ.groupby(["species", "groupe"], as_index=False).agg(
        nom_commun=("nom_commun", "first"),
        n_obs=("key", "count"),
        uicn=("uicn", "first"),
        protege_fr=("protege_fr", "max"),
        directive=("directive", "first"),
        sens=("sens_solaire", "first"),
        n_zip_zer=("zone", lambda z: z.isin(["ZIP", "ZER"]).sum()),
        derniere_annee=("year", "max"),
        enjeu=("enjeu", worst),
        enjeu_regl=("enjeu_regl", worst),
    )
    s["protege_fr"] = s.protege_fr.map({True: "Oui", False: "Non"})
    s = s.rename(
        columns={
            "species": "Nom scientifique",
            "groupe": "Groupe",
            "nom_commun": "Nom commun",
            "n_obs": "Nb observations",
            "uicn": "Statut UICN",
            "protege_fr": "Protection FR",
            "directive": "Directive UE",
            "sens": "Sensibilité solaire",
            "n_zip_zer": "Nb obs ZIP/ZER",
            "derniere_annee": "Dernière année",
            "enjeu": "Enjeu",
            "enjeu_regl": "Enjeu réglementaire brut",
        }
    )
    key = s.Enjeu.map(ORDER)
    return (
        s.assign(_o=key)
        .sort_values(["_o", "Nb observations"], ascending=[True, False])
        .drop(columns="_o")
    )


def prospection(occ: pd.DataFrame, zer_km2: float) -> dict:
    """Observation effort in ZIP+ZER: counts, richness, and an under-prospected warning."""
    sub = occ[occ.zone.isin(["ZIP", "ZER"])]
    top = occ.groupby("source").size().sort_values(ascending=False).head(5)
    return {
        "n_zer": len(sub),
        "n_esp_zer": sub.species.nunique(),
        "par_km2": len(sub) / max(zer_km2, 1e-9),
        "sous": len(sub) < 100 or sub.species.nunique() < 40,
        "sources": top,
        "n_sources": occ.source.nunique(),
    }


def landscape_context(zip_, zer, zee, reservoirs: gpd.GeoDataFrame, occ: gpd.GeoDataFrame) -> dict:
    """Is the site inside a reservoir, next to one, or a gap ("dent creuse")?

    Compares the **share of patrimonial records** (patrimonial / all recent records, which damps
    the uneven observer effort) in ZER outside protected areas vs inside protected areas.
    """
    rec = occ[~occ.donnee_historique].copy()
    zf = reservoirs[reservoirs.kind.isin(STRONG_KINDS)]
    zall = reservoirs.geometry.union_all() if len(reservoirs) else None
    rec["en_zonage"] = rec.intersects(zall) if zall is not None else False
    rec["secteur"] = np.select(
        [rec.zone.isin(["ZIP", "ZER"]) & ~rec.en_zonage, rec.en_zonage],
        ["ZER hors zonage", "Dans zonage"],
        "ZEE hors ZER/zonage",
    )
    a_zon = zee.intersection(zall).area / 1e6 if zall is not None else 0.0
    a_zer_zon = zer.intersection(zall).area / 1e6 if zall is not None else 0.0
    areas = {
        "ZER hors zonage": zer.area / 1e6 - a_zer_zon,
        "Dans zonage": a_zon,
        "ZEE hors ZER/zonage": (zee.area - zer.area) / 1e6 - (a_zon - a_zer_zon),
    }
    rows, share = [], {}
    for sector, km2 in areas.items():
        d = rec[rec.secteur == sector]
        pat = d[d.patrimoniale]
        share[sector] = len(pat) / len(d) if len(d) else 0.0
        rows.append(
            [
                sector,
                f"{km2:.2f}",
                len(d),
                f"{len(d) / km2:.0f}" if km2 > 0.01 else "n.c.",
                pat.species.nunique(),
                len(pat),
                f"{share[sector] * 100:.1f} %",
            ]
        )
    table = pd.DataFrame(
        rows,
        columns=[
            "Secteur",
            "Surface km²",
            "Obs récentes",
            "Obs/km²",
            "Esp. patrimoniales",
            "Obs patrimoniales",
            "Part d'obs patrimoniales",
        ],
    )
    d_fort = float(zip_.distance(zf.geometry.union_all())) if len(zf) else None
    in_fort = bool(len(zf) and zf.intersects(zip_).any())
    p_zer, p_zon = share["ZER hors zonage"], share["Dans zonage"]
    ratio = p_zer / p_zon if p_zon else float("nan")
    cmp_txt = (
        f"part d'observations patrimoniales {p_zer * 100:.1f} % en ZER contre "
        f"{p_zon * 100:.1f} % dans les zonages"
    )
    if in_fort:
        text = "Site inclus dans un réservoir de biodiversité (ZNIEFF I / Natura 2000)."
    elif d_fort is not None and d_fort < 1000 and ratio < 0.6:
        text = (
            f"Dent creuse / zone périphérique : site hors zonage fort mais à {d_fort:.0f} m d'un "
            f"réservoir ; {cmp_txt}. Intérêt écologique propre limité, "
            "rôle de zone tampon à vérifier."
        )
    elif d_fort is not None and d_fort < 1000:
        text = (
            f"Site en périphérie immédiate d'un réservoir ({d_fort:.0f} m), de richesse "
            f"patrimoniale comparable ou supérieure ({cmp_txt}) : il peut fonctionner comme annexe "
            "d'habitat (chasse, nidification) du réservoir."
        )
    else:
        text = (
            "Matrice agricole ou naturelle banale, éloignée de tout réservoir fort : pas de "
            "fonction de réservoir identifiée."
        )
    return {
        "table": table,
        "text": text,
        "d_fort": d_fort,
        "in_fort": in_fort,
        "cov_zer": a_zer_zon / (zer.area / 1e6),
        "cov_zee": a_zon / (zee.area / 1e6),
        "rec": rec,
    }


# National action plans (PNA) worth screening for any development project.
PNA = [
    ("Lézard ocellé", ["Timon lepidus", "Lacerta lepida"]),
    ("Faucon crécerellette", ["Falco naumanni"]),
    ("Cistude d'Europe", ["Emys orbicularis"]),
    ("Aigle royal", ["Aquila chrysaetos"]),
    ("Pie-grièche à tête rousse", ["Lanius senator"]),
    ("Aigle de Bonelli", ["Aquila fasciata", "Hieraaetus fasciatus"]),
]


def pna_table(occ: pd.DataFrame, coarse: pd.DataFrame | None = None) -> pd.DataFrame:
    """Presence of PNA species, odonates and bats per zone (all years) + imprecise records."""
    rows = []
    co = coarse if coarse is not None else pd.DataFrame(columns=occ.columns)

    def line(label: str, d: pd.DataFrame, dc: pd.DataFrame) -> None:
        z = d.zone.value_counts()
        n_zer = int(z.get("ZIP", 0) + z.get("ZER", 0))
        if len(d) == 0 and len(dc) == 0:
            note = "Aucune donnée GBIF"
        elif len(d) == 0:
            note = "Signalé dans le secteur, positions imprécises (maille de 5 km)"
        else:
            note = "Signalé dans la ZER (1 km)" if n_zer else "Signalé en ZEE uniquement (1 à 5 km)"
        last = (
            d.year.max() if d.year.notna().any() else (dc.year.max() if len(dc) else float("nan"))
        )
        rows.append(
            [
                label,
                int(z.get("ZIP", 0)),
                n_zer,
                len(d),
                len(dc),
                "-" if pd.isna(last) else int(last),
                note,
            ]
        )

    for label, species in PNA:
        line(label, occ[occ.species.isin(species)], co[co.species.isin(species)] if len(co) else co)
    line(
        "Odonates (ordre)",
        occ[occ["order"] == "Odonata"],
        co[co["order"] == "Odonata"] if len(co) else co,
    )
    line(
        "Chiroptères (ordre)",
        occ[occ.groupe == "Chiroptères"],
        co[co.groupe == "Chiroptères"] if len(co) else co,
    )
    cols = [
        "PNA / groupe",
        "Obs. ZIP",
        "Obs. ZIP+ZER",
        "Obs. ZEE",
        "Obs. imprécises",
        "Dernière année",
        "Lecture",
    ]
    return pd.DataFrame(rows, columns=cols)


def protected_table(zip_, reservoirs: gpd.GeoDataFrame, rec: gpd.GeoDataFrame) -> pd.DataFrame:
    """Protected areas by distance to the footprint, with their patrimonial species count."""
    if reservoirs.empty:
        return pd.DataFrame()
    pts = gpd.sjoin(
        rec[rec.patrimoniale][["species", "geometry"]],
        reservoirs[["nom", "type", "geometry"]],
        predicate="within",
    )
    rows = []
    for (kind, name), z in reservoirs.groupby(["type", "nom"]):
        dist = zip_.distance(z.geometry.union_all())
        n = pts[(pts["type"] == kind) & (pts["nom"] == name)].species.nunique()
        rows.append([kind, name, dist / 1000, "Oui" if dist == 0 else "Non", n])
    df = pd.DataFrame(
        rows, columns=["Zonage", "Nom", "d", "Recouvre l'emprise", "Esp. patrimoniales GBIF (ZEE)"]
    ).sort_values("d")
    df = df[df.d <= 5.0]  # protected areas within the ZEE
    df["Distance à l'emprise"] = df.d.map(
        lambda v: "0 km" if v == 0 else f"{v:.2f} km".replace(".", ",")
    )
    return df[
        [
            "Zonage",
            "Nom",
            "Distance à l'emprise",
            "Recouvre l'emprise",
            "Esp. patrimoniales GBIF (ZEE)",
        ]
    ]


def shared_species_table(reservoirs: gpd.GeoDataFrame, rec: gpd.GeoDataFrame, top: int = 30):
    """Patrimonial species seen inside protected areas, and whether they occur near the site."""
    empty = pd.DataFrame()
    if reservoirs.empty:
        return empty, 0, 0
    pts = gpd.sjoin(
        rec[rec.patrimoniale][["species", "geometry"]], reservoirs[["geometry"]], predicate="within"
    )
    base = (
        pts.groupby("species")
        .size()
        .rename("obs_zonage")
        .reset_index()
        .merge(
            rec[
                ["species", "uicn", "directive", "protege_fr", "sens_solaire", "groupe"]
            ].drop_duplicates("species"),
            on="species",
        )
    )
    near = rec[rec.zone.isin(["ZIP", "ZER"])].groupby("species").size().rename("obs_zer")
    zipc = rec[rec.zone == "ZIP"].groupby("species").size().rename("obs_zip")
    df = base.merge(near, on="species", how="left").merge(zipc, on="species", how="left")
    df[["obs_zer", "obs_zip"]] = df[["obs_zer", "obs_zip"]].fillna(0).astype(int)
    df["Statut"] = [
        " ; ".join(
            x
            for x in [
                "Prot. nat." if r.protege_fr else "",
                r.directive,
                r.uicn if r.uicn in ("CR", "EN", "VU", "NT") else "",
            ]
            if x
        )
        for r in df.itertuples()
    ]
    df["Présence"] = [
        "Sur l'emprise" if z else "ZER" if n else "Non signalée"
        for z, n in zip(df.obs_zip, df.obs_zer, strict=True)
    ]
    df = df.sort_values(["obs_zer", "obs_zonage"], ascending=False)
    n_shared, n_zip = int((df.obs_zer > 0).sum()), int((df.obs_zip > 0).sum())
    out = df[
        ["species", "groupe", "Statut", "sens_solaire", "obs_zonage", "obs_zer", "Présence"]
    ].head(top)
    out.columns = [
        "Espèce",
        "Groupe",
        "Statut",
        "Sensibilité solaire",
        "Obs. zonages",
        "Obs. ZER",
        "Présence près du site",
    ]
    return out, n_shared, n_zip


def incidences(rec: pd.DataFrame) -> pd.DataFrame:
    """Patrimonial species of ZIP+ZER ordered by solar sensitivity then observations."""
    zs = rec[rec.patrimoniale & rec.zone.isin(["ZIP", "ZER"])].assign(
        nom_commun=lambda d: d.nom_commun.fillna("")
    )
    inc = (
        zs.groupby(["groupe", "species", "nom_commun", "sens_solaire"])
        .size()
        .rename("n")
        .reset_index()
    )
    rank = inc.sens_solaire.map({"Forte": 0, "Modérée": 1, "Faible": 2})
    return inc.assign(_o=rank).sort_values(["_o", "n"], ascending=[True, False]).drop(columns="_o")
