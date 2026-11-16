"""AOI-only environmental data diagnostic: give a project footprint, get a desk-based ecology dossier.

Ties the pure engines to the ScruTech sources so the user supplies only an emprise:

- occurrences: GBIF (:mod:`biodiag.gbif`) over the wide study zone (ZEE), every year, split into
  precise records (stakes) and coarse records (> 1 km, sensitivity analysis);
- protected areas: INPN layers on the Géoplateforme WFS (:mod:`biodiag.environment`);
- stakes and landscape reading: :mod:`biodiag.enjeux`; distance bands, flora, motorway, habitats:
  :mod:`biodiag.proximite`; species reasoning: :mod:`biodiag.justification`;
- outputs: maps, processing diagram, CSV for the R script, Markdown and PDF report.

Products land in the ScruTech store, ``{SCRUTECH_DATA}/biodiag/aoi={aoi_id}/output/``.
CLI: ``biodiag <aoi> [--zer 1000 --zee 5000]`` with ``<aoi>`` = ``insee:XXXXX``, a vector file or
``minx,miny,maxx,maxy`` (WGS84).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
from core.aoi import Aoi, resolve_aoi
from core.constants import L93, WGS84
from core.io import read_vector
from core.storage import product_path

from biodiag import (
    cartes,
    enjeux,
    environment,
    gbif,
    maps,
    pdf,
    proximite,
    report,
    schemas,
    tableaux,
    taxa,
)

logger = logging.getLogger("biodiag")


def run_biodiag(
    aoi: object,
    out_dir: Path | None = None,
    *,
    zer_m: int = 1000,
    zee_m: int = 5000,
    zonage_radius_m: int = 6000,
    habitat: str = "",
    intro: str = "",
    control: str = "",
    project: dict | None = None,
    exclude_kinds: tuple[str, ...] = (),
    ref: str = "",
    title: str | None = None,
    logo: Path | None = None,
    brand: str = "scrutech",
    from_year: int = 1990,
    progress=None,
) -> dict[str, Path]:
    """Run the whole diagnostic for the AOI (the footprint). Returns the written files."""
    say = progress or (lambda _p, _m: None)
    a: Aoi = resolve_aoi(aoi)
    out = Path(out_dir) if out_dir else product_path("biodiag", a.aoi_id, "output")
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "cache"
    footprint = a.to_l93()
    zip_, zer, zee = enjeux.make_zones(footprint, zer_m, zee_m)
    label = title or a.label

    say(10, "Occurrences GBIF…")
    zee_wgs = gpd.GeoSeries([zee], crs=L93).to_crs(WGS84).iloc[0]
    raw = gbif.fetch_occurrences(zee_wgs, cache / f"gbif_{a.aoi_id}.parquet")
    meta = raw.attrs.get("meta", {})
    occ, coarse, counts = gbif.clean_all(raw, from_year)
    occ = taxa.classify(occ)
    coarse = taxa.classify(
        coarse.drop_duplicates(["species", "decimalLatitude", "decimalLongitude", "eventDate"])
    )

    say(35, "Zonages de protection (INPN)…")
    reservoirs = environment.fetch_protected_areas(zip_.buffer(max(zonage_radius_m, zee_m)))
    reservoirs = reservoirs[~reservoirs.kind.isin(exclude_kinds)].reset_index(drop=True)
    names = gbif.names_and_sources(occ, cache / "gbif_names.json")
    names = gbif.names_and_sources(coarse[coarse.patrimoniale], cache / "gbif_names.json")

    say(50, "Enjeux, distances et contexte…")
    occ = enjeux.qualify(occ, (zip_, zer, zee), reservoirs, names)
    occ = proximite.add_bands(occ, zip_)
    syn = enjeux.species_summary(occ)
    pressure = enjeux.prospection(occ, zer.area / 1e6)
    ctx = enjeux.landscape_context(zip_, zer, zee, reservoirs, occ)
    env = environment.fetch_environment(zip_, zer, zee)
    sp_band, obs_band = proximite.species_by_band(occ)
    pat_band = proximite.patrimonial_by_band(occ)
    flora = proximite.flora_summary(occ)
    motorway_density = (
        proximite.density_by_motorway_distance(occ, env["autoroute"], zee)
        if env["autoroute"] is not None
        else pd.DataFrame()
    )
    bias = proximite.observer_bias(occ, env["autoroute"], env["aires"])
    habitats = proximite.habitats_table(zer, env["veg_all"], reservoirs, zip_)
    veg = env["veg_all"]
    open_ha = float(
        sum(veg[veg.nature.isin(["Vigne", "Verger", "Lande ligneuse"])].intersection(zer).area) / 1e4
    ) if len(veg) else 0.0  # fmt: skip
    hedge_ha = (
        float(veg[veg.nature == "Haie"].intersection(zer).area.sum() / 1e4) if len(veg) else 0.0
    )
    hydro = env["hydro"]
    basin = (
        hydro[hydro.nature.str.contains("bassin", case=False, na=False)] if len(hydro) else hydro
    )
    facts = {
        "area_ha": zip_.area / 1e4, "open_ha": open_ha, "hedge_ha": hedge_ha,
        "d_water": env["eau"][1] if env["eau"] else 0.0,
        "d_basin": float(basin.d.min()) if len(basin) else 0.0,
    }  # fmt: skip
    hab_facts = {"zer_ha": zer.area / 1e4, **facts}

    n2k = tableaux.n2k_notes(reservoirs, zip_, occ, names, coarse)
    n2k_species = set().union(*(s["species_latin"] for s in n2k)) if n2k else set()
    coarse_table, bats, coarse_info = tableaux.coarse_tables(coarse, names, n2k_species)
    precise_patri = set(occ[occ.patrimoniale].species)
    coarse_info["n_patri_new"] = len(coarse_info.get("patri_species", set()) - precise_patri)
    pat_t = tableaux.pat_band_table(occ, pat_band, names)
    justif = tableaux.justif_table(pat_band, facts, names, occ, dmax=1000)
    justif_far = tableaux.justif_table(pat_band, facts, names, occ, dmax=2000, dmin=1000)
    annex_a = tableaux.annex_table(pat_band, occ, coarse_table, names)
    pj = _project_texts(project or {}, zip_.area)

    say(75, "Cartes et schéma…")
    cartes.map_situation(zip_, zer, zee, reservoirs, occ, out / "carte_situation.png")
    cartes.map_proximity(zip_, zer, occ, env, out / "carte_proximite.png")
    cartes.map_habitats(zip_, zer, reservoirs, env, out / "carte_milieux.png")
    cartes.map_bias(zip_, occ, env, bias, out / "carte_biais_observation.png")
    cartes.map_natura(zip_, reservoirs, out / "carte_natura2000.png")
    prim = pdf.BRANDS[brand].primary
    schemas.processing_diagram(
        counts, meta, out / "schema_traitement.png", "#{:02x}{:02x}{:02x}".format(*prim)
    )
    maps.interactive_map(zip_, zer, zee, reservoirs, occ, out / "carte_interactive.html")
    tableaux.r_exports(
        occ,
        raw[~(raw.year < from_year)],
        coarse,
        sp_band,
        obs_band,
        motorway_density,
        zip_,
        zee,
        out,
    )

    say(88, "Rapport…")
    centre = gpd.GeoSeries([zip_.centroid], crs=L93).to_crs(WGS84).iloc[0]
    zon_t = enjeux.protected_table(zip_, reservoirs, ctx["rec"])
    case = report.Case(
        title=label, area_ha=zip_.area / 1e4, centroid=(centre.y, centre.x), zer_m=zer_m,
        zee_m=zee_m, zer_km2=zer.area / 1e6, zee_km2=zee.area / 1e6,
        rpg=environment.farmland_declared(zip_), habitat=habitat, synthese=syn, pressure=pressure,
        context=ctx, pna=enjeux.pna_table(occ, coarse), protected=zon_t, incidences=enjeux.incidences(ctx["rec"]),
        env=env, counts=counts, meta=meta, sp_band=sp_band, obs_band=obs_band, pat_band=pat_t,
        justif=justif, justif_far=justif_far, flora=flora, motorway={"density": motorway_density}, habitats=habitats,
        hab_facts=hab_facts, coarse=coarse, coarse_info=coarse_info, bats=bats,
        odonata=tableaux.odonata_info(occ, coarse), n2k=n2k, annex_a=annex_a,
        coarse_table=coarse_table, bias=bias, project=pj, ref=ref, intro=intro, control=control,
        images={
            "schema": "schema_traitement.png", "proximite": "carte_proximite.png", "natura": "carte_natura2000.png",
            "situation": "carte_situation.png", "biais": "carte_biais_observation.png",
        },
        figures={p.stem: f"R/sorties/{p.name}" for p in sorted((out / "R" / "sorties").glob("fig_*.png"))},
    )  # fmt: skip
    md = report.build(case)
    files = {
        "markdown": out / "rapport_diagnostic.md",
        "pdf": out / "rapport_diagnostic.pdf",
        "occurrences": out / "occurrences_nettoyees.geojson",
        "species": out / "synthese_enjeux.csv",
        "zonages": out / "zonages.geojson",
        "map": out / "carte_interactive.html",
    }
    files["markdown"].write_text(md, "utf-8")
    sub = f"{label}\n{ref}\nApproche bibliographique : GBIF et zonages INPN".replace("\n\n", "\n")
    pdf.render(
        md, files["pdf"], "Diagnostic par analyse de données environnementales", sub, logo, brand
    )
    annex_md = report.build_annexes(case)
    files["annexes_md"] = out / "annexes.md"
    files["annexes_pdf"] = out / "annexes.pdf"
    files["annexes_md"].write_text(annex_md, "utf-8")
    pdf.render(
        annex_md, files["annexes_pdf"], "Annexes du diagnostic", "", logo, brand, front=False
    )
    occ.to_crs(WGS84).assign(eventDate=lambda d: d.eventDate.astype(str)).drop(
        columns=["iucnRedListCategory", "vernacularName", "bande"]
    ).to_file(files["occurrences"], driver="GeoJSON")
    syn.to_csv(files["species"], index=False, encoding="utf-8-sig", sep=";")
    coarse_table.to_csv(
        out / "observations_imprecises_patrimoniales.csv",
        index=False,
        encoding="utf-8-sig",
        sep=";",
    )
    if len(reservoirs):
        reservoirs.to_crs(WGS84).to_file(files["zonages"], driver="GeoJSON")
    say(100, "Terminé")
    logger.info("Stakes (records): %s", occ.enjeu.value_counts().to_dict())
    return files


def _project_texts(p: dict, area_m2: float) -> dict:
    """Short statements on the soil, only for the facts the developer confirmed."""
    road = p.get("voie_pompier_m2")
    if road is None:
        return {"sol_txt": "", "sol_court": "", "sol_ref": ""}
    share = road / area_m2 * 100
    return {
        "sol_txt": (
            f"Le sol n'est pas remanié, sauf pour la voie d'accès pompier, de moins de {road:.0f} m² "
            f"(environ {share:.0f} % de l'emprise). Elle est accessible depuis l'extérieur du site et assure "
            "la défense incendie de tout le secteur."
        ).replace(".", ".", 1),
        "sol_court": f"Le sol n'est remanié que pour la voie d'accès pompier (moins de {road:.0f} m²).",
        "sol_ref": f"hors voie d'accès pompier (moins de {road:.0f} m²)",
    }


def _read_aoi(spec: str, assume_crs: str | None, filters: list[str]) -> object:
    """AOI argument -> input for :func:`core.aoi.resolve_aoi` (bbox, id, or a filtered file)."""
    parts = spec.split(",")
    if len(parts) == 4:
        try:
            return tuple(float(p) for p in parts)
        except ValueError:
            pass
    if not Path(spec).exists():
        return spec  # insee:XXXXX, dept:XX
    gdf = (
        read_vector(Path(spec))
        if not assume_crs
        else gpd.read_file(spec).set_crs(assume_crs, allow_override=True)
    )
    for f in filters:  # --filter numero=1265,2784
        col, _, values = f.partition("=")
        gdf = gdf[gdf[col].astype(str).isin(values.split(","))]
    return gdf


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="biodiag", description=__doc__.split("\n")[0])
    ap.add_argument("aoi", help="insee:XXXXX | vector file | minx,miny,maxx,maxy (WGS84)")
    ap.add_argument("--zer", type=int, default=1000, help="close study zone buffer, metres")
    ap.add_argument("--zee", type=int, default=5000, help="wide study zone buffer, metres")
    ap.add_argument(
        "--zonage-radius", type=int, default=6000, help="protected-area search radius, m"
    )
    ap.add_argument("--habitat", default="", help="land cover of the footprint (from orthophoto)")
    ap.add_argument("--intro", default="", help="paragraph on why the study exists (a request...)")
    ap.add_argument("--control", default="", help="paragraph on who checked the environmental data")
    ap.add_argument(
        "--project-json", type=Path, help="JSON of project facts (remaniement_sol, ...)"
    )
    ap.add_argument(
        "--without-zonage",
        action="append",
        default=[],
        help="drop a protected-area kind (e.g. pnr)",
    )
    ap.add_argument(
        "--params", type=Path, help="UTF-8 JSON with title, ref, habitat, intro, control"
    )
    ap.add_argument("--from-year", type=int, default=1990, help="ignore records before this year")
    ap.add_argument("--ref", default="", help="dossier reference (e.g. permit number)")
    ap.add_argument("--title", help="report title (default: the AOI label)")
    ap.add_argument("--logo", type=Path, help="PNG logo for the cover page")
    ap.add_argument("--brand", choices=sorted(pdf.BRANDS), default="scrutech", help="PDF colours")
    ap.add_argument("--out", type=Path, help="output folder (default: the ScruTech store)")
    ap.add_argument(
        "--assume-crs", help="CRS to assume when the vector file has none (e.g. EPSG:2154)"
    )
    ap.add_argument("--filter", action="append", default=[], help="keep rows: column=v1,v2")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    if args.params:  # accented text is safer in a UTF-8 file than on a Windows command line
        for k, v in json.loads(args.params.read_text("utf-8")).items():
            setattr(args, k, v)
    aoi = _read_aoi(args.aoi, args.assume_crs, args.filter)
    project = json.loads(args.project_json.read_text("utf-8")) if args.project_json else {}
    files = run_biodiag(
        aoi, args.out, zer_m=args.zer, zee_m=args.zee, zonage_radius_m=args.zonage_radius,
        habitat=args.habitat, intro=args.intro, control=args.control, project=project,
        exclude_kinds=tuple(args.without_zonage), ref=args.ref, title=args.title, logo=args.logo,
        brand=args.brand, from_year=args.from_year,
    )  # fmt: skip
    for kind, path in files.items():
        print(f"{kind}: {path}")


if __name__ == "__main__":
    main()
