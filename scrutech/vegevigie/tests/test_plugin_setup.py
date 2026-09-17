"""QGIS plugin setup helpers (no QGIS needed): GEE key check, engine and Python discovery."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "qgis_plugin"))

from scrutech.algorithms import _setup, _venv  # noqa: E402


def test_gee_key_accepts_a_service_account() -> None:
    key = {
        "type": "service_account",
        "client_email": "scrutech@projet.iam.gserviceaccount.com",
        "private_key": "fausse-cle-de-test",
        "project_id": "projet",
    }
    assert _setup.check_gee_key(json.dumps(key)) == []


def test_gee_key_says_what_is_wrong() -> None:
    assert _setup.check_gee_key("pas du json") == ["le fichier n'est pas un JSON valide"]
    # A user OAuth file instead of a service-account key: wrong type + 3 missing fields.
    assert len(_setup.check_gee_key(json.dumps({"type": "authorized_user"}))) == 4


def test_engine_project_needs_pyproject_and_lock(tmp_path) -> None:
    plugin_root = tmp_path / "plugins" / "scrutech"
    bundled = plugin_root / "engine" / "vegevigie"
    bundled.mkdir(parents=True)
    (bundled / "pyproject.toml").write_text("")
    assert _setup.engine_project(plugin_root) is None
    (bundled / "uv.lock").write_text("")
    assert _setup.engine_project(plugin_root) == bundled


def test_user_venv_is_searched_after_the_dev_venv(tmp_path) -> None:
    candidates = _venv._candidates(tmp_path / "vegevigie" / "qgis_plugin" / "scrutech")
    dev = str(_venv._python_in(tmp_path / "vegevigie" / ".venv"))
    user = str(_venv._python_in(_setup.USER_VENV))
    assert candidates.index(dev) < candidates.index(user)


def test_install_pins_the_engine_python(monkeypatch, tmp_path) -> None:
    seen = {}

    class _Proc:
        stdout: list[str] = []

        def __init__(self, cmd, **_kwargs):
            seen["cmd"] = cmd

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(_setup.subprocess, "Popen", _Proc)
    assert _setup.install_env("uv", tmp_path, lambda _line: None, lambda: False) == 0
    assert seen["cmd"][seen["cmd"].index("--python") + 1] == "3.11"
