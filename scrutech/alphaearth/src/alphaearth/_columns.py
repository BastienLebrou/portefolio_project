"""The 64 AlphaEarth embedding band names (A00…A63)."""

from __future__ import annotations

N_BANDS = 64
# Liste en compréhension : construit ["A00", "A01", ..., "A63"] d'un coup. Le format
# `{i:02d}` affiche i sur 2 chiffres avec un zéro devant si besoin (7 -> "07").
EMB_COLS = [f"A{i:02d}" for i in range(N_BANDS)]
