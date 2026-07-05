"""STAC catalog tests — pure query building, summarizing and caching, no network."""

from pathlib import Path
from typing import Any

from vegevigie.catalog import (
    build_search_params,
    load_cached_items,
    search_and_cache,
    summarize_item,
)


def test_build_search_params() -> None:
    params = build_search_params(
        bbox=(4.5, 44.5, 4.7, 44.6),
        start_year=2020,
        end_year=2020,
        collection="sentinel-2-l2a",
        max_cloud_cover=60,
    )
    assert params["collections"] == ["sentinel-2-l2a"]
    assert params["bbox"] == [4.5, 44.5, 4.7, 44.6]
    assert params["datetime"] == "2020-01-01T00:00:00Z/2020-12-31T23:59:59Z"
    assert params["query"] == {"eo:cloud_cover": {"lt": 60}}


def test_summarize_item() -> None:
    item = {
        "id": "S2B_31TFJ_20200705",
        "properties": {
            "datetime": "2020-07-05T10:26:00Z",
            "eo:cloud_cover": 3.2,
            "s2:mgrs_tile": "31TFJ",
        },
    }
    summary = summarize_item(item)
    assert summary == {
        "id": "S2B_31TFJ_20200705",
        "datetime": "2020-07-05T10:26:00Z",
        "cloud_cover": 3.2,
        "tile": "31TFJ",
    }


class _FakeBackend:
    stac_url = "fake://stac"

    def __init__(self) -> None:
        self.searches = 0

    def search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.searches += 1
        return [{"id": "item-1", "properties": {"datetime": "2020-07-05T10:26:00Z"}}]

    def sign(self, item: dict[str, Any]) -> dict[str, Any]:
        return item


def test_search_and_cache_writes_and_reuses(tmp_path: Path) -> None:
    backend = _FakeBackend()
    params = build_search_params((4.5, 44.5, 4.7, 44.6), 2020, 2020, "sentinel-2-l2a", 60)
    cache = tmp_path / "items.json"

    items = search_and_cache(backend, params, cache)
    assert len(items) == 1
    assert cache.exists()
    assert backend.searches == 1

    # Second call hits the cache, no new search.
    again = search_and_cache(backend, params, cache)
    assert again == items
    assert backend.searches == 1

    # --force triggers a fresh search.
    search_and_cache(backend, params, cache, force=True)
    assert backend.searches == 2


def test_load_cached_items_roundtrip(tmp_path: Path) -> None:
    backend = _FakeBackend()
    params = build_search_params((4.5, 44.5, 4.7, 44.6), 2020, 2020, "sentinel-2-l2a", 60)
    cache = tmp_path / "items.json"
    written = search_and_cache(backend, params, cache)
    assert load_cached_items(cache) == written
