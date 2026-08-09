"""classifier.py tests — RF on synthetic separable embeddings, CV score present."""

import numpy as np
import pandas as pd

from alphaearth._columns import EMB_COLS
from alphaearth.classifier import classify, train_classifier


def _labelled(n_per_class: int = 40) -> pd.DataFrame:
    """Two classes separated by a shift on the first embedding dims (easy for RF)."""
    rng = np.random.RandomState(0)
    rows = []
    for label, shift in (("forêt", -3.0), ("eau", 3.0)):
        block = rng.randn(n_per_class, 64)
        block[:, 0] += shift
        df = pd.DataFrame(block, columns=EMB_COLS)
        df["label"] = label
        rows.append(df)
    return pd.concat(rows, ignore_index=True)


def test_train_reports_a_cv_score_and_fits() -> None:
    trained = train_classifier(_labelled(), cv=4)
    assert set(trained.class_names) == {"forêt", "eau"}
    assert trained.n_samples == 80
    assert trained.cv_accuracy > 0.9  # separable -> RF nails it


def test_classify_adds_prediction_and_confidence() -> None:
    trained = train_classifier(_labelled())
    out = classify(trained, _labelled(n_per_class=10))
    assert {"predicted_class", "confidence"} <= set(out.columns)
    assert out["confidence"].between(0, 1).all()
    assert (
        out["predicted_class"] == out.index.map(lambda i: "forêt" if i < 10 else "eau")
    ).mean() > 0.9
