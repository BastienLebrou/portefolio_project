"""Land-use classification on the 64-D AlphaEarth embeddings — Random Forest.

CE QUE ÇA FAIT : entraîne un classifieur léger sur 50-200 points annotés
(forêt/eau/bâti/culture…) et l'applique à toute l'AOI.

POURQUOI un RF et pas un réseau de neurones : 200 annotations sont bien trop peu pour
entraîner un réseau — mais les embeddings AlphaEarth ont déjà distillé des pétaoctets
de données satellite en 64 features riches ; un RF « choisit » lesquelles discriminent
notre tâche. On **valide toujours** par validation croisée avant de classifier la zone
entière — jamais de résultat sans score.

VULGARISATION : les embeddings font le gros du travail ; le RF ne fait que trier.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from alphaearth._columns import EMB_COLS


@dataclass
class TrainedModel:
    """A fitted classifier plus its honest cross-validation score."""

    model: object
    class_names: list[str]
    cv_accuracy: float
    n_samples: int


def train_classifier(
    samples: pd.DataFrame,
    label_col: str = "label",
    n_estimators: int = 100,
    cv: int = 5,
) -> TrainedModel:
    """Train a RandomForest on ``samples`` (64 ``EMB_COLS`` + ``label_col``).

    Returns the fitted model with a K-fold cross-validation accuracy (never classify
    without a score). Folds are capped by the smallest class so tiny sets don't crash.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score

    x = samples[EMB_COLS].to_numpy(dtype=float)
    y = samples[label_col].to_numpy()
    clf = RandomForestClassifier(n_estimators=n_estimators, n_jobs=-1, random_state=42)

    min_class = int(np.unique(y, return_counts=True)[1].min())
    folds = max(2, min(cv, min_class))
    cv_acc = float("nan")
    if len(y) >= 4 and min_class >= 2:
        cv_acc = float(cross_val_score(clf, x, y, cv=folds).mean())

    clf.fit(x, y)
    return TrainedModel(
        model=clf,
        class_names=sorted({str(v) for v in y}),
        cv_accuracy=cv_acc,
        n_samples=len(y),
    )


def classify(trained: TrainedModel, embeddings: pd.DataFrame) -> pd.DataFrame:
    """Apply ``trained`` to ``embeddings`` (64 ``EMB_COLS``) -> + predicted_class + confidence."""
    x = embeddings[EMB_COLS].to_numpy(dtype=float)
    proba = trained.model.predict_proba(x)  # type: ignore[attr-defined]
    out = embeddings.copy()
    out["predicted_class"] = trained.model.predict(x)  # type: ignore[attr-defined]
    out["confidence"] = proba.max(axis=1)
    return out
