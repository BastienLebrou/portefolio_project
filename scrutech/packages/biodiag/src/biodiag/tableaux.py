"""Report tables and R input files, built from the proximity and stakes results (no network)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

from biodiag import justification, taxa
from biodiag.proximite import BAND_LABELS

DATA = Path(__file__).parent / "data"


def _i(v) -> int | str:
    """Integer, or an empty cell when the value is missing."""
    return "" if pd.isna(v) else int(v)


def common(names: dict, key, species: str | None = None) -> str:
    """French vernacular name (override list first, then GBIF; '' if unknown)."""
    if species in taxa.FR_NAMES:
        return taxa.FR_NAMES[species]
    if pd.isna(key):
        return ""
    return names["nom"].get(str(int(key)), "")


def status(r) -> str:
    """Compact status text: protection, directive, threatened IUCN category."""
    bits = [
        "Prot. nat." if r.protege_fr else "",
        r.directive,
        r.uicn if r.uicn in ("CR", "EN", "VU", "NT") else "",
    ]
    return " ; ".join(b for b in bits if b)


def pat_band_table(
    occ: pd.DataFrame, pat_band: pd.DataFrame, names: dict, dmax: float = 2000
) -> pd.DataFrame:
    """Patrimonial species seen within ``dmax`` m: observations per band, nearest distance."""
    key = occ.drop_duplicates("species").set_index("species").speciesKey
    t = pat_band[pat_band["Distance min. (m)"] <= dmax].copy()
    t.insert(
        0,
        "Espèce",
        [
            f"{s} ({common(names, key.get(s), s)})" if common(names, key.get(s), s) else s
            for s in t.index
        ],
    )
    return t.reset_index(drop=True).drop(columns=["Total"])


def justif_table(
    pat_band: pd.DataFrame,
    facts: dict,
    names: dict,
    occ: pd.DataFrame,
    dmax: float = 2000,
    dmin: float = 0,
) -> pd.DataFrame:
    """Habitat needed and why the project does not affect it, for species seen within ``dmax``."""
    key = occ.drop_duplicates("species").set_index("species").speciesKey
    rows = []
    sel = pat_band[(pat_band["Distance min. (m)"] > dmin) & (pat_band["Distance min. (m)"] <= dmax)]
    for sp, r in sel.iterrows():
        hab, why = justification.justify(sp, r["Distance min. (m)"], facts)
        nom = common(names, key.get(sp), sp)
        rows.append([f"{sp} ({nom})" if nom else sp, f"{int(r['Distance min. (m)'])} m", hab, why])
    return pd.DataFrame(
        rows,
        columns=[
            "Espèce",
            "Distance min.",
            "Habitat de l'espèce",
            "Pourquoi le projet ne l'affecte pas",
        ],
    )


def coarse_tables(
    coarse_cls: pd.DataFrame, names: dict, n2k_species: set[str]
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(patrimonial coarse species table, bats table, info) from classified coarse records."""
    info = {"n_obs": len(coarse_cls), "n_species": int(coarse_cls.species.nunique()) if len(coarse_cls) else 0,
            "median_u": float(coarse_cls.coordinateUncertaintyInMeters.median()) if len(coarse_cls) else 0.0}  # fmt: skip
    if coarse_cls.empty:
        return pd.DataFrame(), pd.DataFrame(), {**info, "n_patri_new": 0}
    g = coarse_cls.groupby(["species", "groupe"], as_index=False).agg(
        key=("speciesKey", "first"), n=("key", "count"), derniere=("year", "max"),
        prec=("coordinateUncertaintyInMeters", "median"), uicn=("uicn", "first"),
        protege_fr=("protege_fr", "max"), directive=("directive", "first"), patri=("patrimoniale", "max"),
    )  # fmt: skip
    g["Nom commun"] = [common(names, k, s) for k, s in zip(g.key, g.species, strict=True)]
    g["Statut"] = [status(r) for r in g.itertuples()]
    g["Site Natura 2000"] = ["oui" if s in n2k_species else "non" for s in g.species]
    patri = g[g.patri].sort_values("n", ascending=False)
    table = patri[
        ["species", "Nom commun", "groupe", "Statut", "n", "derniere", "prec", "Site Natura 2000"]
    ].rename(
        columns={
            "species": "Espèce",
            "groupe": "Groupe",
            "n": "Relevés",
            "derniere": "Dernière année",
            "prec": "Précision médiane (m)",
        }
    )
    table["Précision médiane (m)"] = table["Précision médiane (m)"].round(0).astype("Int64")
    table["Dernière année"] = table["Dernière année"].astype("Int64")
    bats = g[g.groupe == "Chiroptères"].sort_values("n", ascending=False)
    bats_t = bats[["species", "Nom commun", "Statut", "n", "derniere", "Site Natura 2000"]].rename(
        columns={"species": "Espèce", "n": "Relevés", "derniere": "Dernière année"}
    )
    bats_t["Dernière année"] = bats_t["Dernière année"].astype("Int64")
    return (
        table.reset_index(drop=True),
        bats_t.reset_index(drop=True),
        {**info, "patri_species": set(patri.species)},
    )


def annex_table(
    pat_band: pd.DataFrame, occ: pd.DataFrame, coarse_table: pd.DataFrame, names: dict
) -> pd.DataFrame:
    """The big recap table: every patrimonial species, precise bands + coarse records."""
    key = occ.drop_duplicates("species").set_index("species")
    rows = []
    for sp, r in pat_band.iterrows():
        k = key.loc[sp]
        rows.append([sp, common(names, k.speciesKey, sp), k.groupe, status(k), *[int(r[b]) for b in BAND_LABELS], 0,
                     _i(r["Dernière année"]), int(r["Distance min. (m)"])])  # fmt: skip
    seen = {r[0] for r in rows}
    for r in coarse_table.itertuples(index=False):
        if r[0] in seen:
            continue
        rows.append([r[0], r[1], r[2], r[3], 0, 0, 0, 0, 0, _i(r[4]), _i(r[5]), None])
    cols = [
        "Espèce",
        "Nom commun",
        "Groupe",
        "Statut",
        *BAND_LABELS,
        "Imprécises",
        "Dernière année",
        "Distance min. (m)",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["Distance min. (m)"] = df["Distance min. (m)"].map(lambda v: "" if pd.isna(v) else int(v))
    return df.sort_values(["Groupe", "Espèce"]).reset_index(drop=True)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("s" if n > 1 else "")


def odonata_info(occ: pd.DataFrame, coarse_cls: pd.DataFrame) -> dict:
    """Odonata records near the parcels (precise) and in the sector (coarse)."""
    od = occ[occ["order"] == "Odonata"]
    near = od[od.dist_m <= 1000]
    n_co = int((coarse_cls["order"] == "Odonata").sum()) if len(coarse_cls) else 0
    return {
        "txt": (
            f"Les données précises comptent {_plural(len(near), 'observation')} d'odonates à moins de 1 km "
            f"({_plural(near.species.nunique(), 'espèce')}) et {_plural(len(od), 'observation')} dans les 5 km "
            f"({_plural(od.species.nunique(), 'espèce')}). Les observations imprécises en ajoutent {n_co}."
        )
    }


def n2k_notes(
    reservoirs: gpd.GeoDataFrame,
    zip_,
    occ: pd.DataFrame,
    names: dict,
    coarse: pd.DataFrame | None = None,
) -> list[dict]:
    """Natura 2000 sites around the parcels with their official summary (data/natura2000.json)."""
    notes = json.loads((DATA / "natura2000.json").read_text("utf-8"))
    out = []
    sites = reservoirs[reservoirs.kind.isin(["natura2000_zps", "natura2000_sic"])]
    for r in sites.itertuples():
        m = re.search(r"FR\d{7}", str(r.url))
        code = m.group(0) if m else ""
        if code not in notes:
            continue
        n = notes[code]
        near = occ[occ.dist_m <= 1000].species.unique()
        shared = sorted({f"{n['especes'][s]} ({s})" for s in n["especes"] if s in set(near)})
        in_coarse = set(coarse.species) if coarse is not None and len(coarse) else set()
        shared_coarse = sorted(
            {f"{n['especes'][s]} ({s})" for s in n["especes"] if s in in_coarse} - set(shared)
        )
        out.append({**n, "code": code, "dist_km": zip_.distance(r.geometry) / 1000, "shared": shared,
                    "shared_coarse": shared_coarse,
                    "species_latin": set(n["especes"])})  # fmt: skip
    out.sort(key=lambda s: s["dist_km"])
    for i, s in enumerate(out, 1):
        s["i"] = i
    return out


def r_exports(occ: pd.DataFrame, raw: pd.DataFrame, coarse: pd.DataFrame, sp_band: pd.DataFrame, obs_band: pd.DataFrame,
              density: pd.DataFrame, zip_, zee, out: Path) -> None:  # fmt: skip
    """CSV files read by the R script: species per band, observations per year, motorway density."""
    edges = [0, 500, 1000, 2000, 5000]
    areas = [zip_.area / 1e6]
    for i in range(1, len(edges)):
        ring = zip_.buffer(edges[i]).difference(zip_.buffer(edges[i - 1])).intersection(zee)
        areas.append(ring.area / 1e6)
    long = []
    for g in sp_band.index:
        for lab, a in zip(BAND_LABELS, areas, strict=True):
            long.append([g, lab, int(sp_band.loc[g, lab]), int(obs_band.loc[g, lab]), round(a, 4)])
    pd.DataFrame(
        long, columns=["groupe", "bande", "especes", "observations", "surface_km2"]
    ).to_csv(out / "especes_par_bande.csv", index=False, sep=";", encoding="utf-8-sig")
    precise_years = occ.year.value_counts()
    coarse_years = coarse.year.value_counts() if len(coarse) else pd.Series(dtype=int)
    years = sorted(set(raw.year.dropna().astype(int)))
    pd.DataFrame({"annee": years, "precises": [int(precise_years.get(y, 0)) for y in years],
                  "imprecises": [int(coarse_years.get(y, 0)) for y in years]}).to_csv(
        out / "observations_par_annee.csv", index=False, sep=";", encoding="utf-8-sig")  # fmt: skip
    density.to_csv(out / "densite_autoroute.csv", index=False, sep=";", encoding="utf-8-sig")
