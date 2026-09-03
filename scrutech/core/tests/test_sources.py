"""core.sources offline tests — WFS pagination, 2D flatten, AOI clip (requests mocked)."""

from __future__ import annotations

import geopandas as gpd
from shapely.geometry import box

from core import sources


# _FakeResp est un "test double" écrit à la main : une classe qui imite juste assez
# l'interface d'une vraie réponse `requests` (une méthode .json(), une méthode
# .raise_for_status() qui ne fait rien) pour que le code testé s'en satisfasse, sans
# jamais faire de vrai appel réseau. Pas besoin d'une bibliothèque de mock pour ça :
# une petite classe maison suffit quand l'interface à simuler est aussi simple.
class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


def _feature(x: float, y: float, nature: str = "Forêt fermée de feuillus") -> dict:
    # A tiny 3D polygon around (x, y) in L93 metres — Z must be dropped by _force_2d.
    ring = [[x, y, 1.0], [x + 50, y, 1.0], [x + 50, y + 50, 1.0], [x, y + 50, 1.0], [x, y, 1.0]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"cleabs": f"b-{x:.0f}", "nature": nature},
    }


def test_fetch_bdtopo_paginates_flattens_and_clips(monkeypatch) -> None:
    # AOI = a 100 m box in L93 near Ardèche; only the feature inside it must survive the clip.
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.601, 44.501)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    minx, miny, _, _ = resolve_aoi(aoi).to_l93().bounds

    inside = _feature(minx + 5, miny + 5)  # inside the AOI
    outside = _feature(minx + 5_000, miny + 5_000)  # far away → clipped out

    # First page returns PAGE_SIZE-1 features → loop stops after one call (got < page size).
    monkeypatch.setattr(sources, "WFS_PAGE_SIZE", 10)
    calls = {"n": 0}

    def fake_get(url, params, timeout):
        calls["n"] += 1
        return _FakeResp({"features": [inside, outside]})

    # On remplace ici la fonction `get` du MODULE requests lui-même (importé dans
    # sources.py), pas une fonction du projet comme dans les autres tests : ça intercepte
    # tout appel `requests.get(...)` fait depuis `sources`, quelle que soit la fonction
    # interne qui l'appelle.
    monkeypatch.setattr(sources.requests, "get", fake_get)

    gdf = sources.fetch_bdtopo(aoi, "BDTOPO_V3:zone_de_vegetation", ["cleabs", "nature"])
    assert calls["n"] == 1
    assert gdf.crs.to_epsg() == 2154
    assert len(gdf) == 1  # only the inside feature survived the clip
    assert not gdf.geometry.iloc[0].has_z  # 3D flattened to 2D


def test_fetch_forest_keeps_only_forest_natures(monkeypatch) -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    c = resolve_aoi(aoi).to_l93().centroid  # anchor inside the (rotated) AOI polygon
    feats = [
        _feature(c.x - 100, c.y, "Forêt fermée de conifères"),
        _feature(c.x + 100, c.y, "Vigne"),  # not forest → dropped
        _feature(c.x, c.y + 100, "Bois"),
    ]
    monkeypatch.setattr(
        sources.requests, "get", lambda url, params, timeout: _FakeResp({"features": feats})
    )

    forest = sources.fetch_forest(aoi)
    assert set(forest["nature"]) == {"Forêt fermée de conifères", "Bois"}


def test_fetch_biodiversity_reservoirs_combines_kinds(monkeypatch) -> None:
    aoi = gpd.GeoDataFrame(geometry=[box(4.6, 44.5, 4.7, 44.6)], crs="EPSG:4326")
    from core.aoi import resolve_aoi

    c = resolve_aoi(aoi).to_l93().centroid

    def _site(name: str) -> dict:
        ring = [[c.x, c.y], [c.x + 80, c.y], [c.x + 80, c.y + 80], [c.x, c.y + 80], [c.x, c.y]]
        return {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"nom_site": name},
        }

    monkeypatch.setattr(
        sources.requests,
        "get",
        lambda url, params, timeout: _FakeResp({"features": [_site("Site X")]}),
    )

    gdf = sources.fetch_biodiversity_reservoirs(aoi, kinds=("natura2000_sic", "znieff1"))
    assert set(gdf["kind"]) == {"natura2000_sic", "znieff1"}
    assert list(gdf.columns) == ["kind", "nom_site", "geometry"] or "geometry" in gdf.columns
    assert (gdf["nom_site"] == "Site X").all()
    assert gdf.crs.to_epsg() == 2154
