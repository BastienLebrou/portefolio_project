"""Package the ScruTech QGIS plugin into an installable zip.

Bundles inside the plugin folder:

- ``engine/``: the engine source projects (vegevigie, core, ecobuage, biotrame, alphaearth)
  and ``uv.lock``, so « Vérifier et installer ScruTech » can build the external Python with
  ``uv`` on the user's machine (the heavy third-party stack itself is never bundled);
- ``ecobuage.py``: the pure-numpy engine the native écobuage tool imports inside QGIS.

Then zips ``scrutech/`` into ``dist/scrutech.zip``, ready for QGIS ▸ Plugins ▸ Install from
ZIP.

Run: ``python qgis_plugin/package.py``
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO_ROOT = PROJECT.parent  # sibling projects (core, ecobuage, …) live here
PLUGIN = HERE / "scrutech"
DIST = HERE / "dist"
# vegevigie first: its pyproject + uv.lock drive the build, the others are its path deps.
ENGINE_PROJECTS = ("vegevigie", "core", "ecobuage", "biotrame", "alphaearth")
# Only what `uv sync` needs to build them: code, config, pyproject, README, lock.
_SOURCE_IGNORE = shutil.ignore_patterns(
    "qgis_plugin",
    "tests",
    "docs",
    "scripts",
    "notebooks",
    "data",
    ".venv",
    ".*_cache",
    "__pycache__",
    "*.pyc",
    "CLAUDE.md",
    ".pre-commit-config.yaml",
    ".gitignore",
)
# Single-module engines from sibling projects, bundled flat next to the plugin.
EXTRA_MODULES = {"ecobuage": REPO_ROOT / "ecobuage" / "ecobuage.py"}
# Multi-file sibling engines bundled as a folder — code only (data/cache excluded);
# the plugin runs them in an external Python via subprocess.
# ponytail: sdbpi and mini_dc are hidden from the plugin, so nothing is bundled here; add
# {"sdbpi": REPO_ROOT / "sdbpi", "mini_dc": REPO_ROOT / "mini_dc" / "outil"} to ship them.
EXTRA_DIRS: dict[str, Path] = {}
_ENGINE_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "cache",
    "BDD",
    "data",
    ".venv",
    "dist",
    "*.gpkg",
    "*.parquet",
    "*.zip",
    "*.shp",
    "*.dbf",
    "*.shx",
    "*.prj",
    "*.cpg",
    "*.qmd",
)


def bundle_engine_sources() -> None:
    """Copy the engine source projects (with vegevigie's uv.lock) into ``scrutech/engine/``."""
    dest = PLUGIN / "engine"
    if dest.exists():
        shutil.rmtree(dest)
    for name in ENGINE_PROJECTS:
        shutil.copytree(REPO_ROOT / name, dest / name, ignore=_SOURCE_IGNORE)
    print(f"Bundled engine sources -> {dest}")


def bundle_extras() -> None:
    """Copy single-module sibling engines (e.g. ecobuage) flat into the plugin."""
    for name, src in EXTRA_MODULES.items():
        if not src.exists():
            print(f"Skipped '{name}' engine (not found at {src}) — its algorithm won't run.")
            continue
        shutil.copy2(src, PLUGIN / src.name)
        print(f"Bundled {name} -> {PLUGIN / src.name}")


def bundle_extra_dirs() -> None:
    """Copy multi-file sibling engines (sdbpi, mini_dc) into the plugin — code only."""
    for name, src in EXTRA_DIRS.items():
        if not src.exists():
            print(f"Skipped '{name}' engine (not found at {src}) — its algorithm won't run.")
            continue
        dest = PLUGIN / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=_ENGINE_IGNORE)
        print(f"Bundled {name} -> {dest}")


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
    bundle_engine_sources()
    bundle_extras()
    bundle_extra_dirs()
    make_zip()


if __name__ == "__main__":
    main()
