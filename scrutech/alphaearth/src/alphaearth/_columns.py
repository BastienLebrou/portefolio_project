"""The 64 AlphaEarth embedding band names (A00…A63)."""

from __future__ import annotations

N_BANDS = 64
EMB_COLS = [f"A{i:02d}" for i in range(N_BANDS)]
