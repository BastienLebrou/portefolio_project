"""store.py tests — GeoParquet cache roundtrip + idempotence, no network."""

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from alphaearth import store
from alphaearth._columns import EMB_COLS


def _emb_gdf(n: int = 20) -> gpd.GeoDataFrame:
    rng = np.random.RandomState(0)
    df = pd.DataFrame({c: rng.randn(n).astype("float32") for c in EMB_COLS})
    df["pixel_id"] = np.arange(n)
    pts = [Point(4.0 + i * 0.001, 44.0 + i * 0.001) for i in range(n)]
    return gpd.GeoDataFrame(df, geometry=pts, crs="EPSG:4326")


# monkeypatch.setenv définit une VARIABLE D'ENVIRONNEMENT juste pour la durée de ce
# test (elle est restaurée automatiquement après) : ça redirige core.storage.data_root()
# vers le dossier temporaire du test, sans jamais toucher au vrai dossier de données ni
# devoir passer un paramètre explicite à travers toute la chaîne d'appels.
def test_write_then_read_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRUTECH_DATA", str(tmp_path))
    assert not store.has("insee-07005", 2024)
    path = store.write(_emb_gdf(), "insee-07005", 2024, quota_pixels=20)
    assert path.exists()
    assert store.has("insee-07005", 2024)

    back = store.read("insee-07005", 2024)
    assert len(back) == 20
    assert set(EMB_COLS) <= set(back.columns)

    # Provenance side-car written.
    prov = path.with_suffix(".json")
    assert prov.exists()
    import json

    meta = json.loads(prov.read_text(encoding="utf-8"))
    assert meta["aoi_id"] == "insee-07005"
    assert meta["year"] == 2024
    assert meta["n_pixels"] == 20


def test_cache_path_layout(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SCRUTECH_DATA", str(tmp_path))
    p = store.cache_path("insee-07005", 2024)
    assert (
        p
        == tmp_path
        / "alphaearth"
        / "aoi=insee-07005"
        / "embeddings"
        / "2024"
        / "embeddings.parquet"
    )
