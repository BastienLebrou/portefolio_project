"""biodiag tests: statuses, stake rules, GBIF slicing and PDF rendering, all offline."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

from biodiag import gbif, pdf, taxa
from biodiag.enjeux import make_zones, qualify, species_summary

L93 = "EPSG:2154"


def _occ(rows: list[dict]) -> gpd.GeoDataFrame:
    """Classified occurrences from (species, class, kingdom, x, y, year, uicn) dicts."""
    base = {
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Aves",
        "order": "Passeriformes",
        "genus": "X",
        "iucnRedListCategory": "LC",
        "year": 2020,
        "eventDate": "2020-05-01",
        "datasetKey": "d",
        "institutionCode": "i",
        "vernacularName": None,
        "speciesKey": None,
        "precision_inconnue": False,
        "key": 0,
    }
    df = pd.DataFrame([{**base, "key": i, **r} for i, r in enumerate(rows)])
    df["donnee_historique"] = df.year < gbif.RECENT_FROM
    df = taxa.classify(df)
    return gpd.GeoDataFrame(df, geometry=[Point(r["x"], r["y"]) for r in rows], crs=L93)


def test_protection_and_directives() -> None:
    assert taxa.protection("Anthus campestris", "Anthus", "Oiseaux") == (True, "DO Ann. I")
    assert taxa.protection("Columba palumbus", "Columba", "Oiseaux") == (False, "")
    assert taxa.protection("Myotis myotis", "Myotis", "Chiroptères") == (True, "DHFF Ann. II+IV")
    assert taxa.protection("Podarcis muralis", "Podarcis", "Reptiles") == (True, "DHFF Ann. IV")


def test_patrimonial_excludes_common_protected_and_huntable() -> None:
    occ = _occ(
        [
            {"species": "Anthus campestris", "x": 0, "y": 0},
            {"species": "Parus major", "x": 0, "y": 0},
            {
                "species": "Oryctolagus cuniculus",
                "x": 0,
                "y": 0,
                "class": "Mammalia",
                "order": "Lagomorpha",
                "iucnRedListCategory": "EN",
            },
        ]
    )
    got = dict(zip(occ.species, occ.patrimoniale, strict=True))
    assert got == {"Anthus campestris": True, "Parus major": False, "Oryctolagus cuniculus": False}
    assert occ.sensible.tolist() == [True, True, True]  # protected or EN: kept as "sensible"


def test_stakes_by_zone_and_history() -> None:
    zones = make_zones(box(-50, -50, 50, 50), 1000, 5000)
    occ = _occ(
        [
            {"species": "Anthus campestris", "x": 0, "y": 500},  # patrimonial, ZER -> Fort
            {"species": "Anthus campestris", "x": 0, "y": 3000},  # patrimonial, ZEE -> Modéré
            {"species": "Parus major", "x": 0, "y": 500},  # protected common, ZER -> Modéré
            {"species": "Parus major", "x": 0, "y": 3000},  # protected common, ZEE -> Faible
            {
                "species": "Anthus campestris",
                "x": 0,
                "y": 500,
                "year": 1995,
            },  # historical -> Modéré
            {"species": "Anthus campestris", "x": 0, "y": 9000},  # outside ZEE -> dropped
        ]
    )
    empty = gpd.GeoDataFrame({"kind": [], "type": [], "nom": []}, geometry=[], crs=L93)
    out = qualify(occ, zones, empty, {"nom": {}, "ds": {}})
    assert out.enjeu.tolist() == ["Fort", "Modéré", "Modéré", "Faible", "Modéré"]
    assert out.enjeu_regl.iloc[3] == "Modéré"  # the literal rule is kept apart
    syn = species_summary(out)
    assert syn.iloc[0]["Nom scientifique"] == "Anthus campestris" and syn.iloc[0]["Enjeu"] == "Fort"


class _Facets:
    """Fake GBIF facet answer: two datasets, one small and one still too big."""

    def json(self) -> dict:
        counts = [{"name": "small", "count": 3000}, {"name": "big", "count": 9000}]
        return {"facets": [{"counts": counts}]}


def test_split_query_by_dataset_then_year(monkeypatch) -> None:
    monkeypatch.setattr(gbif, "_get", lambda *a, **k: _Facets())
    monkeypatch.setattr(gbif, "_count", lambda q: 5000)  # each year of the big dataset
    got = list(gbif.split_query({}, 12000, limit=8000))
    assert got[0][0]["datasetKey"] == "small" and "year" not in got[0][0]
    years = [q["year"] for q, _ in got if q["datasetKey"] == "big"]
    assert years[0] == "1000,1999" and years[-1] == str(gbif.time.localtime().tm_year)


def test_pdf_renders_markdown_with_table(tmp_path) -> None:
    md = "## 1. Titre\n\nTexte **gras**, *italique* ≤ 5 km.\n\n- point\n\n"
    md += "| a | b |\n|---|---|\n| 1 | é |\n"
    out = tmp_path / "r.pdf"
    pdf.render(md, out, "Titre", "Sous-titre")
    assert out.read_bytes().startswith(b"%PDF")
