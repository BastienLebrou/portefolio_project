"""Écobuage scoring engine: unknown pixels stay unknown, bad criteria are refused clearly."""

from __future__ import annotations

import ecobuage
import numpy as np
import pytest


def test_unknown_score_is_nodata_not_excluded() -> None:
    score = np.array([80.0, 50.0, 10.0, np.nan])
    assert ecobuage.classify(score).tolist() == [2, 1, 0, ecobuage.NODATA_CLASS]


def test_criteria_outside_0_1_are_refused_with_the_likely_cause() -> None:
    ecobuage.check_unit(np.array([0.0, 0.5, 1.0, np.nan]), "Accessibilité")  # fine
    with pytest.raises(ValueError, match="nodata"):
        ecobuage.check_unit(np.array([0.2, -9999.0]), "Accessibilité")
    with pytest.raises(ValueError, match="ne couvre pas"):
        ecobuage.check_unit(np.array([np.nan, np.nan]), "Historique")
