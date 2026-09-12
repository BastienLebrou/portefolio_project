"""Cloud rasters — convertir en COG et lire à distance par plage d'octets.

POURQUOI (packaging). Pour qu'un utilisateur tiers n'ait PAS à télécharger le MNT France de
916 Mo : on le convertit une fois en **COG** (Cloud-Optimized GeoTIFF, tuilé + aperçus) et on
le pose sur un stockage objet (R2/S3). GDAL lit alors **seulement les tuiles de l'emprise** via
``/vsicurl/`` — quelques Mo au lieu du fichier entier. Même principe pour les GeoParquet.

- ``to_cog`` : GeoTIFF -> COG (à lancer côté « producteur », une fois).
- ``raster_source`` : transforme une URL/chemin en chemin GDAL ouvrable (``/vsicurl/`` pour
  http(s), ``/vsis3/`` pour s3://), pour que ``rasterio.open`` lise en distant de façon
  transparente côté « consommateur ».
"""

from __future__ import annotations

from pathlib import Path


def to_cog(
    src: str | Path,
    dst: str | Path,
    *,
    compress: str = "DEFLATE",
    overview_resampling: str = "average",
) -> Path:
    """Convertir un GeoTIFF en Cloud-Optimized GeoTIFF (tuilé + aperçus internes)."""
    from rasterio.shutil import copy as rio_copy

    rio_copy(
        str(src),
        str(dst),
        driver="COG",
        compress=compress,
        overview_resampling=overview_resampling,
    )
    return Path(dst)


def raster_source(path: str | Path) -> str:
    """Chemin GDAL-ouvrable : ``/vsicurl/`` pour http(s), ``/vsis3/`` pour s3://, sinon local.

    Permet à ``rasterio.open(raster_source(mnt))`` de lire indifféremment un MNT local ou un COG
    hébergé (lecture par plage), sans changer le reste du code.
    """
    s = str(path)
    if s.startswith(("http://", "https://")):
        return "/vsicurl/" + s
    if s.startswith("s3://"):
        return "/vsis3/" + s[len("s3://") :]
    return s
