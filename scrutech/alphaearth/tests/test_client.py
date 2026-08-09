"""client.py tests — cost estimate + GEE-response parsing (ee mocked, no network)."""

from alphaearth._columns import EMB_COLS
from alphaearth.client import AlphaEarthQuery, _features_to_gdf, estimate_gee_cost


def test_query_dataclass_defaults() -> None:
    q = AlphaEarthQuery(aoi_geojson={"type": "Point", "coordinates": [4, 44]}, year=2024)
    assert q.max_pixels == 500_000
    assert q.band_indices is None


def test_estimate_cost_scales_and_flags() -> None:
    small = estimate_gee_cost(1.0)  # 1 km² -> 10_000 px
    assert small["pixel_count"] == 10_000
    assert small["quota_impact"] == "faible"
    big = estimate_gee_cost(200.0)  # 200 km² -> 2e6 px
    assert big["quota_impact"] == "élevé"
    assert big["recommendation"] == "exporter par tuiles"


def test_features_to_gdf_parses_a_gee_collection() -> None:
    # A minimal GEE FeatureCollection.getInfo() shape: 2 pixels, 64 bands each.
    feats = []
    for k in range(2):
        props = {c: float(k + i) for i, c in enumerate(EMB_COLS)}
        feats.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [4.0 + k, 44.0]},
                "properties": props,
            }
        )
    gdf = _features_to_gdf(feats)
    assert len(gdf) == 2
    assert set(EMB_COLS) <= set(gdf.columns)
    assert gdf.crs.to_epsg() == 4326
    assert gdf["pixel_id"].tolist() == [0, 1]
    assert gdf.loc[0, "A00"] == 0.0 and gdf.loc[1, "A00"] == 1.0
