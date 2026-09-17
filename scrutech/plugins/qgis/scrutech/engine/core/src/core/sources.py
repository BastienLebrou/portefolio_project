"""AOI-driven data acquisition — the layers every pillar derives from a study area.

CE QUE ÇA FAIT : à partir d'une **seule emprise** (AOI), va chercher en open data les
couches vectorielles dont PAF et Écobuage ont besoin — **bâti**, **forêt**, **routes** —
sans que l'utilisateur ait à fournir la moindre couche. C'est ce qui rend les outils
« emprise seule en entrée ».

Source : BD TOPO® via le WFS Géoplateforme IGN (``data.geopf.fr``), pagination gérée
(COUNT plafonné à 5000/requête → ``STARTINDEX``), géométries 3D aplaties en 2D, résultat
clippé exactement à l'emprise et renvoyé en Lambert-93 (mètres).
"""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

from core.aoi import Aoi, resolve_aoi
from core.constants import L93

logger = logging.getLogger("scrutech")

WFS_URL = "https://data.geopf.fr/wfs/ows"
WFS_PAGE_SIZE = 5000

BUILDINGS_TYPENAME = "BDTOPO_V3:batiment"
VEGETATION_TYPENAME = "BDTOPO_V3:zone_de_vegetation"
ROADS_TYPENAME = "BDTOPO_V3:troncon_de_route"

# Biodiversity reservoirs / protected areas — INPN (patrinat) layers on the Géoplateforme
# WFS, same server as BD TOPO. Verified live 2026-08 (typenames return geometry in L93).
RESERVOIR_TYPENAMES = {
    "natura2000_sic": "patrinat_sic:sic",  # Natura 2000 — Directive Habitats
    "natura2000_zps": "patrinat_zps:zps",  # Natura 2000 — Directive Oiseaux
    "znieff1": "patrinat_znieff1:znieff1",  # ZNIEFF type 1 (secteurs de fort intérêt)
    "znieff2": "patrinat_znieff2:znieff2",  # ZNIEFF type 2 (grands ensembles)
    "ramsar": "patrinat_ramsar:ramsar",  # zones humides d'importance internationale
}
# TVB corridors are regional (SRCE/SRADDET), not on this national WFS — added later.
DEFAULT_RESERVOIR_KINDS = ("natura2000_sic", "natura2000_zps", "znieff1", "znieff2")

# BD TOPO zone_de_vegetation "nature" values that count as forest for the WUI/fuel maths.
# Matched case-insensitively as substrings (covers "Forêt fermée de feuillus", "Bois", …).
FOREST_NATURE_HINTS = ("forêt", "foret", "bois", "haie")


def fetch_buildings(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """All BD TOPO buildings within the AOI (EPSG:2154). Columns: usage_1/2, nature, hauteur."""
    keep = ["cleabs", "usage_1", "usage_2", "nature", "hauteur"]
    return fetch_bdtopo(aoi, BUILDINGS_TYPENAME, keep, timeout=timeout)


def fetch_forest(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """BD TOPO wooded zones within the AOI (EPSG:2154), filtered to forest natures."""
    veg = fetch_bdtopo(aoi, VEGETATION_TYPENAME, ["cleabs", "nature"], timeout=timeout)
    if veg.empty or "nature" not in veg.columns:
        return veg
    nat = veg["nature"].fillna("").str.lower()
    mask = nat.apply(lambda s: any(h in s for h in FOREST_NATURE_HINTS))
    return veg[mask].copy()


def fetch_roads(aoi: object, *, timeout: int = 120) -> gpd.GeoDataFrame:
    """BD TOPO road segments within the AOI (EPSG:2154) — for accessibility/distance."""
    return fetch_bdtopo(aoi, ROADS_TYPENAME, ["cleabs", "nature", "importance"], timeout=timeout)


def fetch_biodiversity_reservoirs(
    aoi: object,
    kinds: tuple[str, ...] | None = None,
    *,
    timeout: int = 120,
) -> gpd.GeoDataFrame:
    """Protected areas / biodiversity reservoirs intersecting the AOI (EPSG:2154).

    Combines the requested INPN layers (default: Natura 2000 SIC + ZPS, ZNIEFF 1 + 2) into
    one GeoDataFrame with a ``kind`` label and the site name — the "enjeu" input of biotrame.
    """
    kinds = kinds or DEFAULT_RESERVOIR_KINDS
    frames = []
    for kind in kinds:
        gdf = fetch_bdtopo(aoi, RESERVOIR_TYPENAMES[kind], ["nom_site"], timeout=timeout)
        if gdf.empty:
            continue
        gdf["kind"] = kind
        if "nom_site" not in gdf.columns:
            gdf["nom_site"] = None
        frames.append(gdf[["kind", "nom_site", "geometry"]])
    if not frames:
        return gpd.GeoDataFrame({"kind": [], "nom_site": []}, geometry=[], crs=L93)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=L93)


def fetch_tvb_corridors(
    aoi: object,
    typename: str,
    *,
    wfs_url: str,
    keep: list[str] | None = None,
    timeout: int = 120,
) -> gpd.GeoDataFrame:
    """Trame Verte et Bleue corridors for the AOI, from a **regional** WFS (SRCE/SRADDET).

    There is no national TVB WFS — each DREAL publishes its SRCE on its own server, with its
    own ``typename``. Pass the region's ``wfs_url`` + ``typename`` (e.g. from the biotrame
    algorithm parameters). Returns the corridor geometries (EPSG:2154), clipped to the AOI.
    """
    # A WFS endpoint is an http(s) service; refuse other schemes (file://, ftp://…) so a bad
    # config value can't make GDAL/requests read something unexpected.
    if not str(wfs_url).lower().startswith(("http://", "https://")):
        raise ValueError(f"TVB WFS URL must be http(s): {wfs_url!r}")
    return fetch_bdtopo(aoi, typename, keep or [], timeout=timeout, wfs_url=wfs_url)


def fetch_bdtopo(
    aoi: object,
    typename: str,
    keep: list[str],
    *,
    timeout: int = 120,
    clip: bool = True,
    wfs_url: str = WFS_URL,
) -> gpd.GeoDataFrame:
    """Fetch one WFS layer within the AOI's bbox (paginated), clipped to the AOI.

    Defaults to the Géoplateforme WFS (BD TOPO / INPN); ``wfs_url`` targets any other WFS 2.0
    endpoint (e.g. a regional DREAL server for the TVB). Returns a GeoDataFrame in EPSG:2154
    with the ``keep`` columns that exist (plus geometry).
    """
    a: Aoi = resolve_aoi(aoi)
    aoi_l93 = a.to_l93()
    minx, miny, maxx, maxy = aoi_l93.bounds

    features = _paginated_wfs(typename, (minx, miny, maxx, maxy), timeout, wfs_url)
    if not features:
        logger.warning("WFS %s: 0 feature for AOI %s", typename, a.aoi_id)
        return gpd.GeoDataFrame({c: [] for c in keep}, geometry=[], crs=L93)

    gdf = gpd.GeoDataFrame.from_features(features, crs=L93)
    gdf = _force_2d(gdf)
    cols = [c for c in keep if c in gdf.columns]
    gdf = gdf[[*cols, "geometry"]].copy()
    if clip:
        gdf = gdf[gdf.intersects(aoi_l93)].copy()
    return gdf


def _paginated_wfs(
    typename: str, bbox_l93: tuple, timeout: int, wfs_url: str = WFS_URL
) -> list[dict]:
    """Page through a WFS GetFeature (EPSG:2154 bbox) and return raw GeoJSON features."""
    minx, miny, maxx, maxy = bbox_l93
    features: list[dict] = []
    start = 0
    while True:
        params = {
            "SERVICE": "WFS",
            "VERSION": "2.0.0",
            "REQUEST": "GetFeature",
            "TYPENAMES": typename,
            "SRSNAME": f"EPSG:{L93.split(':')[1]}",
            # In EPSG:2154 the axis order is (easting, northing) — verified live.
            "BBOX": f"{minx},{miny},{maxx},{maxy},{L93}",
            "COUNT": str(WFS_PAGE_SIZE),
            "STARTINDEX": str(start),
            "OUTPUTFORMAT": "application/json",
        }
        resp = requests.get(wfs_url, params=params, timeout=timeout)
        resp.raise_for_status()
        page = resp.json().get("features", []) or []
        features.extend(page)
        got = len(page)
        start += got
        logger.info("WFS %s: %d features", typename, start)
        if got < WFS_PAGE_SIZE:
            break
        if start > 2_000_000:  # ponytail: guard-rail, tile the AOI if you ever hit this
            logger.warning("WFS %s: hit 2M guard-rail, result truncated", typename)
            break
    return features


def _force_2d(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """BD TOPO returns 3D geometries; flatten to 2D (Z is useless here), keeping the CRS."""
    crs = gdf.crs
    out = gdf.copy()
    out["geometry"] = gpd.GeoSeries(shapely.force_2d(gdf.geometry.values), index=gdf.index, crs=crs)
    return out


# --- IGN elevation (MNT) ----------------------------------------------------------------
# Géoplateforme WMS-R, GeoTIFF float32 in Lambert-93 (verified live 2026-09): LiDAR HD first
# (not flown everywhere yet), RGE ALTI fills its gaps. Nodata sentinels: -9999 / -99999.
WMS_R_URL = "https://data.geopf.fr/wms-r/wms"
MNT_LAYERS = (
    "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",  # LiDAR HD, best, partial
    "ELEVATION.ELEVATIONGRIDCOVERAGE.HIGHRES",  # RGE ALTI, all of France, fills the gaps
)
ORTHO_LAYER = "ORTHOIMAGERY.ORTHOPHOTOS"  # BD ORTHO, 20 cm RGB aerial photos of France
WMS_TILE_PX = 2000  # server max is 5010 px; smaller tiles keep each request light
MNT_MAX_PX = 25_000_000  # ~100 MB of float32: small zones first (e.g. 25 x 25 km at 5 m)
ORTHO_MAX_PX = 25_000_000  # ~75 MB of RGB: 2.5 x 2.5 km at 10 cm, 10 x 10 km at 40 cm


def fetch_mnt(
    aoi: object,
    out_path: Path,
    *,
    resolution: float = 5.0,
    margin_m: float = 0.0,
    timeout: int = 120,
    progress=None,
) -> tuple[Path, dict]:
    """Download the IGN DEM over the AOI tile by tile, mosaic it, write a Lambert-93 GeoTIFF.

    Returns ``(path, info)``. Raises ValueError (in French, for the user) when the grid is too
    large or when the IGN has no elevation for the zone.
    """
    report = progress or (lambda _pct, _msg: None)
    a = resolve_aoi(aoi)
    grid = _l93_grid(a, resolution, margin_m, MNT_MAX_PX, "le MNT", "10 ou 25 m")
    dem = np.full((grid.height, grid.width), np.nan, dtype="float32")
    tiles = grid.tiles()
    for i, (row, col, h, w, bbox) in enumerate(tiles, 1):
        dem[row : row + h, col : col + w] = _mnt_tile(bbox, w, h, timeout)
        report(int(10 + 85 * i / len(tiles)), f"MNT IGN : tuile {i}/{len(tiles)}")

    valid = np.isfinite(dem)
    if not valid.any():
        raise ValueError("Aucune altitude IGN pour cette zone (le MNT IGN couvre la France).")
    grid.write(out_path, dem[np.newaxis], nodata=float("nan"))
    info = {
        "mnt_resolution": resolution,
        "mnt_tiles": len(tiles),
        "mnt_coverage_pct": round(100.0 * float(valid.mean()), 1),
    }
    logger.info("IGN DEM %s: %s", a.aoi_id, info)
    return Path(out_path), info


def fetch_ortho(
    aoi: object,
    out_path: Path,
    *,
    resolution: float = 0.5,
    timeout: int = 120,
    progress=None,
) -> tuple[Path, dict]:
    """Download the IGN aerial photo (BD ORTHO, RGB) over the AOI as one Lambert-93 GeoTIFF.

    The image Segment Anything needs: real colours at 20 cm to a few metres, unlike the 10 m
    Sentinel-2 bands. Same tiling as :func:`fetch_mnt`; raises ValueError (French) if too large.
    """
    report = progress or (lambda _pct, _msg: None)
    a = resolve_aoi(aoi)
    grid = _l93_grid(a, resolution, 0.0, ORTHO_MAX_PX, "l'image aérienne", "1 ou 2 m")
    image = np.zeros((3, grid.height, grid.width), dtype="uint8")
    tiles = grid.tiles()
    for i, (row, col, h, w, bbox) in enumerate(tiles, 1):
        image[:, row : row + h, col : col + w] = _wms_rgb(bbox, w, h, timeout)
        report(int(10 + 85 * i / len(tiles)), f"Image aérienne IGN : tuile {i}/{len(tiles)}")
    grid.write(out_path, image, photometric="RGB")
    info = {"ortho_resolution": resolution, "ortho_tiles": len(tiles), "ortho_px": grid.size}
    logger.info("IGN ortho %s: %s", a.aoi_id, info)
    return Path(out_path), info


class _L93Grid:
    """A north-up Lambert-93 pixel grid, cut in WMS tiles, written as one GeoTIFF."""

    def __init__(self, minx: float, maxy: float, width: int, height: int, res: float) -> None:
        self.minx, self.maxy, self.width, self.height, self.res = minx, maxy, width, height, res

    @property
    def size(self) -> list[int]:
        return [self.width, self.height]

    def tiles(self) -> list[tuple[int, int, int, int, tuple[float, float, float, float]]]:
        """(row, col, height, width, L93 bbox) of each WMS tile, row by row."""
        out = []
        for row in range(0, self.height, WMS_TILE_PX):
            for col in range(0, self.width, WMS_TILE_PX):
                h, w = min(WMS_TILE_PX, self.height - row), min(WMS_TILE_PX, self.width - col)
                bbox = (
                    self.minx + col * self.res,
                    self.maxy - (row + h) * self.res,
                    self.minx + (col + w) * self.res,
                    self.maxy - row * self.res,
                )
                out.append((row, col, h, w, bbox))
        return out

    def write(self, path: Path, bands: np.ndarray, **profile) -> None:
        import rasterio
        from rasterio.transform import from_origin

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        profile = {
            "driver": "GTiff",
            "width": self.width,
            "height": self.height,
            "count": bands.shape[0],
            "dtype": bands.dtype.name,
            "crs": L93,
            "transform": from_origin(self.minx, self.maxy, self.res, self.res),
            "compress": "deflate",
            "tiled": True,
            **profile,
        }
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(bands)


def _l93_grid(
    a: Aoi, resolution: float, margin_m: float, max_px: int, what: str, coarser: str
) -> _L93Grid:
    """The grid covering the AOI at ``resolution``; ValueError (French) above ``max_px``."""
    import math

    minx, miny, maxx, maxy = a.to_l93().bounds
    minx, miny, maxx, maxy = minx - margin_m, miny - margin_m, maxx + margin_m, maxy + margin_m
    width = max(1, math.ceil((maxx - minx) / resolution))
    height = max(1, math.ceil((maxy - miny) / resolution))
    if width * height > max_px:
        raise ValueError(
            f"Zone trop grande pour télécharger {what} à {resolution:g} m ({width} x {height} "
            f"pixels, maximum {max_px // 1_000_000} millions) : réduisez la zone ou prenez des "
            f"pixels plus grands (par exemple {coarser})."
        )
    return _L93Grid(minx, maxy, width, height, resolution)


def _mnt_tile(bbox: tuple, width: int, height: int, timeout: int) -> np.ndarray:
    """One tile: LiDAR HD, with its no-data cells filled from the RGE ALTI."""
    tile = None
    for layer in MNT_LAYERS:
        arr = _wms_elevation(layer, bbox, width, height, timeout)
        tile = arr if tile is None else np.where(np.isfinite(tile), tile, arr)
        if np.isfinite(tile).all():
            break
    return tile


def _wms_elevation(layer: str, bbox: tuple, width: int, height: int, timeout: int) -> np.ndarray:
    """GetMap one elevation layer as a float32 array (NaN where the IGN has no data)."""
    arr = _getmap(layer, bbox, width, height, "image/geotiff", timeout)[0].astype("float32")
    arr[arr < -1000] = np.nan  # ponytail: -9999 / -99999 sentinels; no French land below -1000 m
    return arr


def _wms_rgb(bbox: tuple, width: int, height: int, timeout: int) -> np.ndarray:
    """GetMap the aerial photo as a (3, height, width) uint8 array (JPEG: 20x lighter)."""
    return _getmap(ORTHO_LAYER, bbox, width, height, "image/jpeg", timeout)[:3]


def _getmap(layer: str, bbox: tuple, width: int, height: int, fmt: str, timeout: int) -> np.ndarray:
    """One WMS-R GetMap in Lambert-93, decoded to a (bands, height, width) array."""
    import warnings

    import rasterio
    from rasterio.errors import NotGeoreferencedWarning

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "STYLES": "",
        "CRS": L93,
        "BBOX": ",".join(f"{v:.3f}" for v in bbox),
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": fmt,
    }
    resp = requests.get(WMS_R_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    if not resp.headers.get("content-type", "").startswith("image/"):
        raise RuntimeError(f"IGN : réponse inattendue du service ({resp.text[:200]})")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)  # we georeference the tile
        with rasterio.MemoryFile(resp.content) as mem, mem.open() as ds:
            return ds.read(out_shape=(ds.count, height, width))
