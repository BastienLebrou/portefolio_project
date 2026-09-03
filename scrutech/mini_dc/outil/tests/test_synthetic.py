"""mini_dc offline anchor — the pure geodesy helper (no DuckDB, no network).

Full pipeline validation lives in ``tests_pipeline.run_tests(con)`` (SQL invariants over a
built DuckDB with the spatial extension); that is a DB-integration harness, not a unit test.
This pins the one pure function so a refactor that breaks the AOI centring is caught in CI.
"""

from __future__ import annotations

import generate_synthetic


def test_centre_lambert93_is_in_metropolitan_france() -> None:
    # Le préfixe "_" signale une fonction "privée" (usage interne au module) : rien
    # n'empêche techniquement de l'appeler depuis un test, et c'est légitime ici pour
    # isoler UNE petite fonction pure plutôt que de repasser par tout generer().
    x, y = generate_synthetic._centre_lambert93()
    # Lambert-93 bounds of metropolitan France (metres), loosely.
    assert 100_000 < x < 1_300_000
    assert 6_000_000 < y < 7_200_000
