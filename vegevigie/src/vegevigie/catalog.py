"""STAC search over the AOI, asset signing, and a cached item list.

**STAC** (SpatioTemporal Asset Catalog) is a JSON standard for describing
geospatial imagery so it can be searched by space / time / collection. We query
Microsoft **Planetary Computer**'s public STAC API for ``sentinel-2-l2a`` scenes,
filter by scene-level cloud cover, and cache the returned item list as JSON in
``data/raw`` so later stages (and reruns) don't re-hit the network.

Two Planetary-Computer specifics worth knowing:

- **Signing.** Asset hrefs are protected by short-lived tokens; you must call
  ``planetary_computer.sign(item)`` before a loader can read the COGs. Signed URLs
  expire, so we cache the *unsigned* items and re-sign at load time (M2) rather
  than caching stale tokens.
- **Backend seam.** All provider specifics live behind :class:`StacBackend` so a
  Copernicus Data Space (CDSE) backend can be dropped in later without touching
  callers (CLAUDE.md §2).

The pure query-building and caching helpers are unit-tested offline; the live
search needs network access to ``planetarycomputer.microsoft.com``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger("vegevigie")

PLANETARY_COMPUTER_STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

BBox = tuple[float, float, float, float]


def build_search_params(
    bbox: BBox,
    start_year: int,
    end_year: int,
    collection: str,
    max_cloud_cover: float,
) -> dict[str, Any]:
    """Build the STAC search kwargs (pure).

    ``datetime`` covers whole calendar years inclusively; ``eo:cloud_cover`` filters
    scenes above the configured ceiling server-side, before we ever download.
    """
    return {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": f"{start_year}-01-01T00:00:00Z/{end_year}-12-31T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud_cover}},
    }


def summarize_item(item: dict[str, Any]) -> dict[str, Any]:
    """Extract the human-facing fields from a STAC item dict (pure)."""
    props = item.get("properties", {})
    return {
        "id": item.get("id"),
        "datetime": props.get("datetime"),
        "cloud_cover": props.get("eo:cloud_cover"),
        "tile": props.get("s2:mgrs_tile") or props.get("grid:code"),
    }


class StacBackend(Protocol):
    """Provider adapter: search returns raw item dicts; sign refreshes asset hrefs."""

    stac_url: str

    def search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Run a STAC search and return items as GeoJSON-like dicts."""
        ...

    def sign(self, item: Any) -> Any:
        """Return the item (pystac Item or dict) with its asset hrefs signed."""
        ...


class PlanetaryComputerBackend:
    """Default backend: Microsoft Planetary Computer public STAC + PC signing."""

    stac_url = PLANETARY_COMPUTER_STAC_URL

    def search(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        # Imported lazily so the module (and its pure helpers/tests) load without
        # the network stack installed or reachable.
        import pystac_client

        client = pystac_client.Client.open(self.stac_url)
        search = client.search(**params)
        items = [item.to_dict() for item in search.items()]
        logger.info("STAC search returned %d items", len(items))
        return items

    def sign(self, item: Any) -> Any:
        import planetary_computer

        return planetary_computer.sign(item)


def search_and_cache(
    backend: StacBackend,
    params: dict[str, Any],
    cache_path: Path,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Search via ``backend``, cache the (unsigned) item list as JSON, return it.

    Idempotent: an existing cache is reused unless ``force``. We deliberately cache
    unsigned items — PC signing tokens expire, so signing is redone at load time.
    """
    if not force and cache_path.exists():
        logger.info("Using cached item list at %s (use --force to refresh)", cache_path)
        return load_cached_items(cache_path)

    items = backend.search(params)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"params": params, "items": items}, indent=2))
    logger.info("Cached %d items to %s", len(items), cache_path)
    return items


def load_cached_items(cache_path: Path) -> list[dict[str, Any]]:
    """Load a cached item list written by :func:`search_and_cache`."""
    payload = json.loads(cache_path.read_text())
    return payload["items"]
