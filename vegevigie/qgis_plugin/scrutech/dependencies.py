"""Runtime dependency check for the VegeVigie datacube stack.

QGIS ships its own Python without the remote-sensing stack. Rather than fail with
a cryptic ``ImportError`` deep in a run, we check up front and hand the user the
exact ``pip`` line for *their* QGIS interpreter.
"""

from __future__ import annotations

import sys

# import name -> pip distribution name (only where they differ).
REQUIRED: dict[str, str] = {
    "pystac_client": "pystac-client",
    "planetary_computer": "planetary-computer",
    "odc.stac": "odc-stac",
    "xarray": "xarray",
    "rioxarray": "rioxarray",
    "rasterio": "rasterio",
    "dask": "dask",
    "geopandas": "geopandas",
    "pymannkendall": "pymannkendall",
    "duckdb": "duckdb",
    "pydantic": "pydantic",
    "yaml": "pyyaml",
}


def missing_dependencies() -> list[str]:
    """Return the pip names of dependencies that fail to import."""
    import importlib

    missing = []
    for module, dist in REQUIRED.items():
        try:
            importlib.import_module(module)
        except Exception:  # noqa: BLE001 — any import failure means "install it"
            missing.append(dist)
    return missing


def install_hint(missing: list[str]) -> str:
    """Explain how to satisfy the datacube stack, recommending an external venv."""
    pkgs = " ".join(missing)
    return (
        "ScruTech needs the VegeVigie datacube stack, which is not available in QGIS's "
        f"Python.\n\nMissing: {pkgs}\n\n"
        "RECOMMENDED — don't install into QGIS (rasterio/GDAL can clash with QGIS's own "
        "GDAL). Instead point the algorithm's 'Python executable' parameter at a venv "
        "that already has the stack, e.g. the project's uv venv:\n"
        "    <repo>/vegevigie/.venv/Scripts/python.exe   (Windows)\n"
        "    <repo>/vegevigie/.venv/bin/python            (macOS/Linux)\n"
        "ScruTech then runs the engine there and only loads the result layers.\n\n"
        "ALTERNATIVELY, install into QGIS's Python via the OSGeo4W Shell "
        "(Start ▸ QGIS ▸ OSGeo4W Shell), then restart QGIS:\n"
        f"    python -m pip install {pkgs}\n\n"
        f"(This QGIS runtime is: {sys.executable})\n"
        "See the plugin README for details."
    )
