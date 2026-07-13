"""Package the ScruTech QGIS plugin into an installable zip.

Bundles the ``vegevigie`` engine package and its ``config/default.yaml`` inside the
plugin folder (so QGIS can import it without a separate install of the *pure*
code), then zips ``scrutech/`` into ``dist/scrutech.zip`` — ready for
QGIS ▸ Plugins ▸ Install from ZIP.

The heavy third-party deps (odc-stac, xarray, pystac-client, …) are NOT bundled;
they must be pip-installed into QGIS's Python (the plugin checks and tells you).

Run: ``python qgis_plugin/package.py``
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO_ROOT = PROJECT.parent  # sibling projects (ecobuage, sdbpi, …) live here
PLUGIN = HERE / "scrutech"
ENGINE_SRC = PROJECT / "src" / "vegevigie"
CONFIG_SRC = PROJECT / "config" / "default.yaml"
# Single-module engines from sibling projects, bundled flat next to the plugin.
EXTRA_MODULES = {"ecobuage": REPO_ROOT / "ecobuage" / "ecobuage.py"}
DIST = HERE / "dist"


def bundle_engine() -> None:
    """Copy the vegevigie package + default config into the plugin folder."""
    dest_pkg = PLUGIN / "vegevigie"
    if dest_pkg.exists():
        shutil.rmtree(dest_pkg)
    shutil.copytree(ENGINE_SRC, dest_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    dest_cfg = PLUGIN / "config"
    dest_cfg.mkdir(exist_ok=True)
    shutil.copy2(CONFIG_SRC, dest_cfg / "default.yaml")
    print(f"Bundled engine -> {dest_pkg}")
    print(f"Bundled config -> {dest_cfg / 'default.yaml'}")


def bundle_extras() -> None:
    """Copy single-module sibling engines (e.g. ecobuage) flat into the plugin."""
    for name, src in EXTRA_MODULES.items():
        if not src.exists():
            print(f"Skipped '{name}' engine (not found at {src}) — its algorithm won't run.")
            continue
        shutil.copy2(src, PLUGIN / src.name)
        print(f"Bundled {name} -> {PLUGIN / src.name}")


def make_zip() -> Path:
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / "scrutech.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN.rglob("*")):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            zf.write(path, path.relative_to(HERE))
    print(f"Wrote {zip_path}")
    return zip_path


def main() -> None:
    bundle_engine()
    bundle_extras()
    make_zip()


if __name__ == "__main__":
    main()
