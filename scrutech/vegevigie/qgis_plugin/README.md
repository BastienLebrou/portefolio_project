# ScruTech: QGIS plugin

QGIS Processing tools for the ScruTech pillars: VegeVigie, AlphaEarth, PAFF, écobuage,
Biotrame and GeoAI. **User instructions live inside QGIS**: each tool's help panel says, in
French, what it does, what it needs, the steps and what it produces.

## Install

1. Build the zip: `python qgis_plugin/package.py` writes `qgis_plugin/dist/scrutech.zip`
   (plugin + engine sources + `uv.lock`, not the heavy third-party stack).
2. QGIS ▸ Plugins ▸ Manage and Install Plugins ▸ Install from ZIP.
3. Processing Toolbox ▸ ScruTech ▸ **0 · Démarrer ici ▸ Vérifier et installer ScruTech**:
   tick *Installer*, Run. It builds the engines' Python with `uv` in `~/.scrutech/venv`
   (about 1 GB, once) and checks internet, the Google Earth Engine key and the DEM. A
   message in QGIS points new users to it.

For development, link `qgis_plugin/scrutech` into the QGIS profile's `python/plugins/`
folder and run `package.py` once; the tools then use `scrutech/vegevigie/.venv`.

## Design

- Heavy engines never run in QGIS's own Python (pip-installed GDAL clashes with QGIS's):
  each tool writes a JSON spec and runs `python -m vegevigie.qgis_runner` in the external
  Python, streaming `PROGRESS` / `RESULT` lines (`algorithms/_external.py`).
- Finding and building that Python: `algorithms/_venv.py` and `algorithms/_setup.py`.
- The two « 5 · Outils avancés » tools and « Communes d'un département » use native QGIS
  only: no external Python needed.
- Download security checklist (GeoAI models): `TODO.md`.
