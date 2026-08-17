"""core.storage offline tests — the layout is the contract, so pin it."""

from pathlib import Path

from core.storage import ENV_ROOT, data_root, db_path, product_path


def test_data_root_honours_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    assert data_root() == tmp_path
    assert db_path() == tmp_path / "scrutech.duckdb"


def test_product_path_layout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    p = product_path("vegevigie", "insee-07005", "trend", "2018_2025", "sen_slope.tif")
    assert p == tmp_path / "vegevigie" / "aoi=insee-07005" / "trend" / "2018_2025" / "sen_slope.tif"


def test_product_path_without_window_or_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ENV_ROOT, str(tmp_path))
    assert product_path("paf", "insee-07005", "interface") == (
        tmp_path / "paf" / "aoi=insee-07005" / "interface"
    )


def test_cache_outputs_and_list_roundtrip(monkeypatch, tmp_path) -> None:
    import core.storage as storage

    monkeypatch.setenv("SCRUTECH_DATA", str(tmp_path))
    # Each pillar caches only its own output folder (realistic).
    bio = tmp_path / "bio_run"
    bio.mkdir()
    (bio / "biotrame_priority.geojson").write_text("{}")
    (bio / "biotrame_priority.parquet").write_bytes(b"")
    (bio / "biotrame_priority.qml").write_text("<qgis/>")
    eco = tmp_path / "eco_run"
    eco.mkdir()
    (eco / "ecobuage_classes.tif").write_bytes(b"")

    storage.cache_outputs("bbox-1", "biotrame", list(bio.glob("*")))
    storage.cache_outputs("bbox-1", "ecobuage", list(eco.glob("*")))

    cached = storage.list_cached("bbox-1")
    names = sorted(p.name for p in cached)
    # geojson + tif kept; the .parquet twin of the geojson is deduped out; .qml not loadable.
    assert names == ["biotrame_priority.geojson", "ecobuage_classes.tif"]
    # sibling .qml travelled with the geojson.
    geojson = next(p for p in cached if p.suffix == ".geojson")
    assert geojson.with_suffix(".qml").exists()
    assert storage.list_cached("bbox-absent") == []
