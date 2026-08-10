"""change.py tests — cosine distance + year-over-year detection, no network."""

import numpy as np
import pandas as pd

from alphaearth._columns import EMB_COLS
from alphaearth.change import cosine_distance, detect_change


def test_cosine_distance_identical_is_zero() -> None:
    a = np.random.RandomState(0).randn(5, 64)
    assert np.allclose(cosine_distance(a, a), 0.0, atol=1e-9)


def test_cosine_distance_opposite_is_two() -> None:
    a = np.random.RandomState(1).randn(3, 64)
    assert np.allclose(cosine_distance(a, -a), 2.0, atol=1e-9)


def _emb(rng: np.random.RandomState, n: int) -> pd.DataFrame:
    data = {c: rng.randn(n) for c in EMB_COLS}
    data["pixel_id"] = np.arange(n)
    return pd.DataFrame(data)


def test_detect_change_flags_the_moved_pixels() -> None:
    rng = np.random.RandomState(42)
    t1 = _emb(rng, 100)
    t2 = t1.copy()
    # Perturb 5 pixels hard; the 95th-percentile threshold should flag ~them.
    for pid in (0, 1, 2, 3, 4):
        t2.loc[pid, EMB_COLS] = rng.randn(64) * 10
    out = detect_change(t1, t2, threshold_percentile=95.0)
    assert set(out.columns) >= {"pixel_id", "change_distance", "changed"}
    assert out["changed"].sum() >= 1
    # The strongly perturbed pixels are among the most-changed.
    top5 = set(out.sort_values("change_distance", ascending=False)["pixel_id"].head(5))
    assert len({0, 1, 2, 3, 4} & top5) >= 3


def test_flag_by_percentile_marks_top_and_reports_threshold() -> None:
    from alphaearth.change import flag_by_percentile

    d = np.array([0.0, 0.1, 0.2, 0.3, 0.9])
    changed, thr = flag_by_percentile(d, percentile=80.0)
    assert changed.tolist() == [False, False, False, False, True]  # only 0.9 above p80
    assert 0.3 <= thr <= 0.9


def test_flag_by_percentile_empty_is_safe() -> None:
    from alphaearth.change import flag_by_percentile

    changed, thr = flag_by_percentile(np.array([]), 95.0)
    assert changed.size == 0 and thr == 0.0
