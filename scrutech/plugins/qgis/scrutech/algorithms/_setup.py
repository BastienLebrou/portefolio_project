"""The engine environment helpers, shared with the ScruTech desktop app.

The real code lives in ``engine_env`` (packages/engine-env), bundled flat next to the plugin by
``package.py`` so QGIS can import it without the engine stack. This module keeps the name the
algorithms already use.
"""

from __future__ import annotations

from engine_env import (  # noqa: F401 — re-exported for the algorithms
    DEFAULT_GEE_KEY,
    ENV_SIZE,
    ENV_STRIP,
    USER_VENV,
    UV_HOME,
    UV_MISSING,
    UV_VERSION,
    check_env,
    check_gee_access,
    check_gee_key,
    download_uv,
    engine_project,
    find_uv,
    install_env,
    install_problem,
    save_gee_key,
    uv_asset,
)
