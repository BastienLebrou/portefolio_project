"""Generate the M2 NDVI-masking demo figure from a SYNTHETIC scene.

This is a teaching/validation artifact, not real data: the live Sentinel-2 path
needs network access to Planetary Computer, which the CI/web egress policy blocks.
We build a plausible NDVI field with clouds + shadow and a matching SCL band, then
show that :func:`vegevigie.indices.masked_ndvi` blanks exactly the flagged pixels.
Swap the synthetic arrays for a real ``cube`` slice once egress is available and
the same code produces the real DoD figure.

Run: ``uv run python scripts/demo_ndvi_masking.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from vegevigie.indices import compute_ndvi, masked_ndvi

DOCS = Path(__file__).resolve().parents[1] / "docs"


def synthetic_scene(size: int = 200, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (red, nir, scl) for a fake but realistic Sentinel-2 scene.

    A vegetation gradient (fields greener toward the south-west), two bright cloud
    blobs and a cloud-shadow strip, with an SCL band labelling them.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size] / size

    # Base surface reflectance: vegetation stronger (higher NIR, lower Red) SW.
    veg = 0.75 - 0.5 * (xx + yy) / 2 + rng.normal(0, 0.02, (size, size))
    red = np.clip(0.18 - 0.10 * veg, 0.02, 0.4)
    nir = np.clip(0.20 + 0.55 * veg, 0.05, 0.6)
    scl = np.full((size, size), 4, dtype="uint8")  # 4 = vegetation everywhere to start

    # Two clouds (bright in both bands -> low NDVI) labelled SCL 9 (cloud high).
    for cy, cx, r in [(0.30, 0.65, 0.13), (0.62, 0.35, 0.10)]:
        blob = (yy - cy) ** 2 + (xx - cx) ** 2 < r**2
        red[blob] = 0.45 + rng.normal(0, 0.02, blob.sum())
        nir[blob] = 0.48 + rng.normal(0, 0.02, blob.sum())
        scl[blob] = 9

    # Cloud-shadow strip (dark) south-east of the first cloud, labelled SCL 3.
    shadow = (yy - 0.42) ** 2 + (xx - 0.78) ** 2 < 0.06**2
    red[shadow] = 0.06
    nir[shadow] = 0.10
    scl[shadow] = 3

    return red, nir, scl


def main() -> None:
    red, nir, scl = synthetic_scene()
    raw = compute_ndvi(red, nir)
    masked = masked_ndvi(red, nir, scl)

    kept = np.isfinite(masked).mean() * 100
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.4))
    cmap = plt.get_cmap("RdYlGn").copy()
    cmap.set_bad("#4a4a4a")  # masked pixels rendered dark grey

    axes[0].imshow(raw, cmap=cmap, vmin=-0.2, vmax=0.9)
    axes[0].set_title("Raw NDVI\n(clouds drag values down)")

    axes[1].imshow(scl, cmap="tab10", vmin=0, vmax=11)
    axes[1].set_title("SCL classes\n(9=cloud, 3=shadow, 4=veg)")

    im = axes[2].imshow(masked, cmap=cmap, vmin=-0.2, vmax=0.9)
    axes[2].set_title(f"SCL-masked NDVI\n{kept:.0f}% pixels kept")

    for ax in axes:
        ax.set_axis_off()
    fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02, label="NDVI")
    fig.suptitle(
        "VegeVigie M2 — SCL cloud masking on NDVI (SYNTHETIC demo; real scene pending egress)",
        fontsize=11,
    )
    out = DOCS / "ndvi_masking_demo.png"
    fig.savefig(out, dpi=130, bbox_inches="tight")
    print(f"wrote {out}  ({kept:.1f}% valid pixels retained)")


if __name__ == "__main__":
    main()
