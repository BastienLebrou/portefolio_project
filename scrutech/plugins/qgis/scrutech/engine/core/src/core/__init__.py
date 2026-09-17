"""ScruTech shared geodata core."""

from core.aoi import Aoi, resolve_aoi
from core.io import read_vector, write_geoparquet

__all__ = ["Aoi", "read_vector", "resolve_aoi", "write_geoparquet"]
