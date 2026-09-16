"""core.cog tests — COG conversion + GDAL source path mapping (no network)."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.transform import from_origin

from core.cog import raster_source, to_cog


def test_raster_source_prefixes_urls() -> None:
    assert raster_source("https://r2.example/mnt.tif") == "/vsicurl/https://r2.example/mnt.tif"
    assert raster_source("s3://bucket/mnt.tif") == "/vsis3/bucket/mnt.tif"
    assert raster_source("C:/data/mnt.tif") == "C:/data/mnt.tif"  # local path unchanged


def test_to_cog_produces_a_readable_cog(tmp_path) -> None:
    src = tmp_path / "src.tif"
    with rasterio.open(
        src,
        "w",
        driver="GTiff",
        width=512,
        height=512,
        count=1,
        dtype="float32",
        crs="EPSG:2154",
        transform=from_origin(900_000, 6_400_000, 10, 10),
    ) as dst:
        dst.write(np.random.RandomState(0).rand(512, 512).astype("float32"), 1)

    cog = to_cog(src, tmp_path / "out.tif")
    assert cog.exists()
    with rasterio.open(cog) as ds:
        assert ds.driver in ("GTiff", "COG")  # COG is a GTiff with an enforced layout
        assert ds.read(1).shape == (512, 512)


def test_require_lambert93_refuses_other_crs() -> None:
    import pytest
    from rasterio.crs import CRS

    from core.cog import require_lambert93

    require_lambert93(None)  # untagged: still assumed Lambert-93
    require_lambert93(CRS.from_epsg(2154))
    with pytest.raises(ValueError, match="degrés"):
        require_lambert93(CRS.from_epsg(4326))  # e.g. Copernicus DEM
    with pytest.raises(ValueError, match="EPSG:32631"):
        require_lambert93(CRS.from_epsg(32631))
