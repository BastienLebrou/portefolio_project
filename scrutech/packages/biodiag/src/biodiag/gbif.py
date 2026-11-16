"""GBIF occurrences around a footprint: paginated download, cleaning, species names.

The GBIF search API caps ``offset + limit`` at 100 000 and answers deep offsets very slowly, so a
big zone is **split into slices** (year, then month, then dataset) of at most ``SLICE_MAX``
records and the pages of all slices are fetched in parallel (4 workers: more triggers HTTP 429).
Only the columns the diagnostic needs are kept, so a 100k-record zone caches in a few MB.
"""

from __future__ import annotations

import calendar
import json
import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from core.constants import L93, WGS84
from shapely import wkt
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

logger = logging.getLogger("biodiag")

API = "https://api.gbif.org/v1"
HEADERS = {"User-Agent": "scrutech-biodiag/0.1 (desk biodiversity diagnostic)"}
PAGE = 300  # GBIF maximum page size
SLICE_MAX = 8000  # above this, a slice is split further (deep offsets get very slow)
RECENT_FROM = 2010  # older records are kept but flagged "historical"
MAX_UNCERTAINTY_M = 1000  # coordinate uncertainty above this is rejected

COLUMNS = [
    "key",
    "scientificName",
    "species",
    "genus",
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "speciesKey",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "year",
    "eventDate",
    "datasetKey",
    "recordedBy",
    "institutionCode",
    "iucnRedListCategory",
    "vernacularName",
    "basisOfRecord",
]


def _get(url: str, params: dict | None = None, tries: int = 8, timeout: int = 60):
    """GET with growing back-off (GBIF answers 429 when hammered); ``None`` after the last try."""
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            logger.warning("HTTP %s on %s", r.status_code, url)
        except requests.RequestException as exc:
            logger.warning("Network error (%s), try %d/%d", type(exc).__name__, i + 1, tries)
        time.sleep(3 * (i + 1) ** 2)
    return None


def search_wkt(geom_wgs84: BaseGeometry) -> str:
    """Counter-clockwise WKT polygon GBIF accepts (simplified ~30 m, convex hull if multipart)."""
    p = geom_wgs84.simplify(0.0003)
    if p.geom_type != "Polygon":
        p = p.convex_hull
    assert isinstance(p, Polygon)
    return orient(p, 1.0).wkt


def _count(q: dict) -> int:
    r = _get(f"{API}/occurrence/search", {**q, "limit": 0})
    return r.json()["count"] if r else 0


def split_query(q: dict, n: int, limit: int = SLICE_MAX) -> Iterator[tuple[dict, int]]:
    """Yield ``(query, count)`` slices of at most ``limit`` records: dataset, year, month, week.

    Dataset first because every record has a dataset, whereas a year or month filter silently drops
    the records where that field is not filled in. Year and month are only used inside a dataset
    that is still too big (deep offsets are very slow on the GBIF API).
    """
    if n <= limit:
        yield q, n
    elif "datasetKey" not in q:
        r = _get(
            f"{API}/occurrence/search", {**q, "limit": 0, "facet": "datasetKey", "facetLimit": 1000}
        )
        for f in r.json()["facets"][0]["counts"] if r else []:
            yield from split_query({**q, "datasetKey": f["name"]}, f["count"], limit)
    elif "year" not in q:
        for yr in [
            {"year": "1000,1999"},
            *({"year": str(y)} for y in range(2000, time.localtime().tm_year + 1)),
        ]:
            qy = {**q, **yr}
            if ny := _count(qy):
                yield from split_query(qy, ny, limit)
    elif "month" not in q:
        for m in range(1, 13):
            qm = {**q, "month": m}
            if nm := _count(qm):
                yield from split_query(qm, nm, limit)
    elif "eventDate" not in q:
        y, m = int(str(q["year"])), int(q["month"])
        last = calendar.monthrange(y, m)[1]
        for d1, d2 in [(1, 7), (8, 14), (15, 21), (22, last)]:
            qd = {**q, "eventDate": f"{y}-{m:02d}-{d1:02d},{y}-{m:02d}-{d2:02d}"}
            if nd := _count(qd):
                yield from split_query(qd, nd, limit)
    else:
        yield q, n  # one dataset, one week, still huge: kept whole (rare)


def fetch_occurrences(geom_wgs84: BaseGeometry, cache: Path | None = None) -> pd.DataFrame:
    """All present, georeferenced FR occurrences inside the polygon (slim columns).

    ``cache`` is a Parquet file reused when it was built for a polygon that contains this one.
    """
    search = search_wkt(geom_wgs84)
    wkt_file = cache.with_suffix(".wkt") if cache else None
    if cache and wkt_file and cache.exists() and wkt_file.exists():
        cached_zone = wkt.loads(wkt_file.read_text())
        if cached_zone.buffer(1e-4).contains(wkt.loads(search)):
            logger.info("GBIF: cache %s", cache.name)
            df = pd.read_parquet(cache)
            meta_file = cache.with_suffix(".meta.json")
            if meta_file.exists():
                df.attrs["meta"] = json.loads(meta_file.read_text("utf-8"))
            return df
    base = {
        "geometry": search,
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "country": "FR",
    }
    total = _count(base)
    if not total:
        raise RuntimeError("GBIF unreachable or no occurrence in the zone")
    logger.info("GBIF: %d occurrences announced", total)

    slices = list(split_query(base, total))
    announced = total
    planned = sum(c for _, c in slices)
    tasks = [(s, off) for s, c in slices for off in range(0, min(c, 100000), PAGE)]
    logger.info(
        "GBIF: %d pages to download (%d announced, %d planned)", len(tasks), announced, planned
    )
    lost = 0

    def page(task: tuple[dict, int]) -> list[dict]:
        q, off = task
        r = _get(f"{API}/occurrence/search", {**q, "limit": PAGE, "offset": off})
        if r is None:
            logger.error("Page lost: %s offset=%d", q.get("year"), off)
            nonlocal lost
            lost += 1
            return []
        return [{c: row.get(c) for c in COLUMNS} for row in r.json()["results"]]

    rows: list[dict] = []
    with ThreadPoolExecutor(4) as ex:
        for k, res in enumerate(ex.map(page, tasks)):
            rows += res
            if k % 50 == 0:
                logger.info("  %d/%d pages, %d occurrences", k, len(tasks), len(rows))
    df = pd.DataFrame(rows, columns=COLUMNS)
    meta = {
        "annoncees": announced, "planifiees": planned, "telechargees": len(df),
        "pages": len(tasks), "pages_perdues": lost, "date": time.strftime("%Y-%m-%d"),
    }  # fmt: skip
    logger.info("GBIF completeness: %s", meta)
    df.attrs["meta"] = meta
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache)
        cache.with_suffix(".wkt").write_text(search)
        cache.with_suffix(".meta.json").write_text(json.dumps(meta), "utf-8")
    return df


def clean_all(
    df: pd.DataFrame, from_year: int = 1990
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, dict]:
    """Split raw records into precise (L93 points), coarse (> 1 km) and the step-by-step counts.

    Coarse records sit at a grid-cell centre (a few km of uncertainty): they cannot say whether a
    species was seen on the footprint, so they stay out of the stakes, but they are returned so
    the report can use them as a sensitivity check instead of silently dropping them.
    """
    counts = {"telecharge": len(df), "from_year": from_year}
    too_old = df.year < from_year  # records without a year are kept
    counts["avant_periode"] = int(too_old.sum())
    df = df[~too_old]
    if len(df):
        counts["annee_min"] = int(df.year.min())
        counts["annee_max"] = int(df.year.max())
    df = df.dropna(subset=["decimalLatitude", "decimalLongitude"]).copy()
    counts["avec_coordonnees"] = len(df)
    df = df.dropna(subset=["species"]).copy()
    counts["rang_espece"] = len(df)
    df["precision_inconnue"] = df.coordinateUncertaintyInMeters.isna()
    coarse = df[df.coordinateUncertaintyInMeters > MAX_UNCERTAINTY_M].copy()
    df = df[df.precision_inconnue | (df.coordinateUncertaintyInMeters <= MAX_UNCERTAINTY_M)]
    counts["imprecis"] = len(coarse)
    counts["precis"] = len(df)
    df = df.drop_duplicates(subset=["species", "decimalLatitude", "decimalLongitude", "eventDate"])
    counts["doublons"] = counts["precis"] - len(df)
    df["donnee_historique"] = df.year.fillna(0) < RECENT_FROM
    counts["retenues"] = len(df)
    counts["historiques"] = int(df.donnee_historique.sum())
    counts["sans_precision"] = int(df.precision_inconnue.sum())
    logger.info("Cleaning: %s", counts)
    pts = gpd.points_from_xy(df.decimalLongitude, df.decimalLatitude)
    gdf = gpd.GeoDataFrame(df, geometry=pts, crs=WGS84).to_crs(L93).reset_index(drop=True)
    return gdf, coarse, counts


def clean(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Precise, de-duplicated records only (see :func:`clean_all`)."""
    return clean_all(df)[0]


def names_and_sources(occ: pd.DataFrame, cache: Path | None = None) -> dict:
    """French vernacular names (per species key) and dataset titles, cached as JSON."""
    c = json.loads(cache.read_text("utf-8")) if cache and cache.exists() else {"nom": {}, "ds": {}}

    def name(k: str) -> tuple[str, str]:
        r = _get(f"{API}/species/{k}/vernacularNames", {"limit": 100}, tries=2, timeout=20)
        fr = [
            v["vernacularName"]
            for v in (r.json()["results"] if r else [])
            if v.get("language") == "fra"
        ]
        return k, (fr[0] if fr else "")

    def title(k: str) -> tuple[str, str]:
        r = _get(f"{API}/dataset/{k}", tries=2, timeout=20)
        return k, (r.json().get("title", k) if r else k)

    species = [str(int(k)) for k in occ.speciesKey.dropna().unique() if str(int(k)) not in c["nom"]]
    datasets = [k for k in occ.datasetKey.dropna().unique() if k not in c["ds"]]
    with ThreadPoolExecutor(8) as ex:
        c["nom"].update(dict(ex.map(name, species)))
        c["ds"].update(dict(ex.map(title, datasets)))
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(c, ensure_ascii=False), "utf-8")
    return c
