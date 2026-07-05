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
    """A copy-pasteable message telling the user how to install into QGIS Python."""
    pkgs = " ".join(missing)
    return (
        "ScruTech needs the VegeVigie datacube stack, which is not installed in this "
        "QGIS Python environment.\n\n"
        f"Missing: {pkgs}\n\n"
        "Install it into *this* interpreter (OSGeo4W Shell on Windows, or your QGIS "
        "Python), for example:\n"
        f'    "{sys.executable}" -m pip install {pkgs}\n\n'
        "Then restart QGIS. See the plugin README for details."
    )
