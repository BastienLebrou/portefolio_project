"""Zero-shot raster segmentation with Meta's Segment Anything Model (SAM).

CE QUE ÇA FAIT : segmente automatiquement un raster (n'importe quelle image satellite ou
aérienne) en objets géoréférencés — sans aucun entraînement. SAM (Apache-2.0, Meta AI)
généralise depuis 1 milliard de masques annotés ; on l'appelle via ``segment-geospatial``
(MIT, Qiusheng Wu — opengeos), qui géoréférence directement les masques.

POURQUOI un modèle téléchargé plutôt qu'un service cloud : contrairement au pilier
AlphaEarth (servi uniquement sur Earth Engine), SAM tourne 100% localement, hors ligne
après le premier téléchargement — pas de quota, pas de clé API.

SÉCURITÉ DU TÉLÉCHARGEMENT (voir aussi qgis_plugin/TODO.md) : Meta ne publie aucun sha256
officiel pour ses checkpoints (vérifié sur le README de facebookresearch/segment-anything —
seuls les liens de téléchargement y figurent). On ne peut donc pas "vérifier contre
l'officiel" comme pour un paquet pip signé. On applique un TOFU (trust-on-first-use, le
modèle des clés SSH) : premier téléchargement depuis l'URL officielle pinée en dur, en
HTTPS ; le sha256 obtenu est persisté à côté du poids ; toute réutilisation revérifie le
fichier local contre ce pin. Ça détecte une corruption/altération du fichier local après
coup — pas une substitution dès le tout premier téléchargement (MITM), limite honnête du
TOFU documentée plutôt que cachée.
"""

from __future__ import annotations

import hashlib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

MODEL_TYPE = "vit_b"  # smallest of the 3 official checkpoints (~375 MB) — plenty for a demo.
MODEL_NAME = "sam_vit_b_01ec64.pth"
MODEL_URL = f"https://dl.fbaipublicfiles.com/segment_anything/{MODEL_NAME}"
MODEL_LICENSE = "Apache-2.0 (Meta AI — github.com/facebookresearch/segment-anything)"

ProgressFn = Callable[[int, str], None]


def default_cache_dir() -> Path:
    """Where downloaded weights live — outside the git repo, outside the plugin folder."""
    return Path.home() / ".scrutech" / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(cache_dir: Path | None = None, progress: ProgressFn | None = None) -> Path:
    """Return a local, checksum-pinned SAM checkpoint, downloading it once if needed."""
    cache_dir = cache_dir or default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    weights = cache_dir / MODEL_NAME
    pin_file = weights.with_suffix(weights.suffix + ".sha256")

    def log(pct: int, msg: str) -> None:
        if progress is not None:
            progress(pct, msg)

    if weights.exists() and pin_file.exists():
        digest = _sha256(weights)
        if digest == pin_file.read_text().strip():
            log(100, f"Using cached, checksum-verified SAM checkpoint: {weights}")
            return weights
        raise RuntimeError(
            f"{weights} no longer matches its pinned checksum (local file changed after "
            "download). Delete it and re-run to re-download from the official source."
        )

    log(
        0,
        f"Downloading SAM checkpoint ({MODEL_TYPE}, ~375 MB, {MODEL_LICENSE})\n  from {MODEL_URL}",
    )
    tmp = weights.with_suffix(weights.suffix + ".part")
    with urllib.request.urlopen(MODEL_URL) as resp, tmp.open("wb") as out:  # noqa: S310 — pinned https URL
        total = int(resp.headers.get("Content-Length", 0)) or None
        read = 0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            read += len(chunk)
            if total:
                log(min(99, int(read * 100 / total)), f"Downloading… {read // (1 << 20)} MB")
    digest = _sha256(tmp)
    tmp.rename(weights)
    pin_file.write_text(digest)
    log(100, f"Downloaded and pinned SAM checkpoint (sha256={digest[:12]}…).")
    return weights


@dataclass
class SegmentResult:
    """Outputs of one segmentation run."""

    mask_tif: Path
    vector_gpkg: Path
    n_objects: int


def segment_raster(
    raster_path: str,
    out_dir: Path,
    checkpoint: Path | None = None,
    points_per_side: int = 32,
    min_mask_region_area: int = 100,
    progress: ProgressFn | None = None,
) -> SegmentResult:
    """Segment ``raster_path`` into georeferenced objects with SAM — no training needed."""
    try:
        from samgeo import SamGeo
    except ImportError as exc:
        raise RuntimeError(
            "segment-geospatial is not installed in this interpreter. Install the "
            "optional 'geoai' extra in the VegeVigie venv:\n"
            "    uv sync --extra geoai\n"
            "or:\n"
            "    pip install segment-geospatial torch"
        ) from exc

    def log(pct: int, msg: str) -> None:
        if progress is not None:
            progress(pct, msg)

    ckpt = checkpoint or ensure_model(progress=progress)
    out_dir.mkdir(parents=True, exist_ok=True)
    mask_tif = out_dir / "geoai_segments.tif"
    vector_gpkg = out_dir / "geoai_segments.gpkg"

    log(10, "Loading SAM…")
    sam = SamGeo(
        model_type=MODEL_TYPE,
        checkpoint=str(ckpt),
        sam_kwargs={
            "points_per_side": points_per_side,
            "min_mask_region_area": min_mask_region_area,
        },
    )

    log(30, "Segmenting (automatic mask generation)…")
    sam.generate(raster_path, output=str(mask_tif))

    log(80, "Vectorizing masks…")
    sam.tiff_to_gpkg(str(mask_tif), str(vector_gpkg))

    import geopandas as gpd

    n_objects = len(gpd.read_file(vector_gpkg))
    log(100, f"Segmented {n_objects} object(s).")
    return SegmentResult(mask_tif=mask_tif, vector_gpkg=vector_gpkg, n_objects=n_objects)
