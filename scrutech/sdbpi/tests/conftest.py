"""Put the SDBPi flat modules (sdbpi_config, sdbpi_processing, …) on the path for tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
