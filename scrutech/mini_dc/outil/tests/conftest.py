"""Put the mini_dc flat modules (config, generate_synthetic, …) on the path for tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
