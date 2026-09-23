"""Make the QGIS plugin and the shared stdlib modules importable from the tests.

The plugin is not a package of this project (it ships on its own), and ``engine_env`` /
``scrutech_styles`` are flat modules bundled next to it: the tests import them from their
source folders, the way ``package.py`` lays them out for QGIS.
"""

import sys
from pathlib import Path

_SCRUTECH = Path(__file__).resolve().parents[3]
for path in (_SCRUTECH / "plugins" / "qgis", _SCRUTECH / "packages" / "engine-env"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
