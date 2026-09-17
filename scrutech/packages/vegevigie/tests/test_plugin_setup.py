"""QGIS plugin setup helpers (no QGIS needed): GEE key check, engine and Python discovery."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "plugins" / "qgis"))

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
    candidates = _venv._candidates(tmp_path / "plugins" / "qgis" / "scrutech")
    dev = str(_venv._python_in(tmp_path / "packages" / "vegevigie" / ".venv"))
    user = str(_venv._python_in(_setup.USER_VENV))
    assert candidates.index(dev) < candidates.index(user)


def test_install_pins_the_engine_python(monkeypatch, tmp_path) -> None:
    seen = {}

    class _Proc:
        stdout: list[str] = []

        def __init__(self, cmd, env, **_kwargs):
            seen["cmd"], seen["env"] = cmd, env

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(_setup.subprocess, "Popen", _Proc)
    assert _setup.install_env("uv", tmp_path, lambda _line: None, lambda: False) == 0
    assert seen["cmd"][seen["cmd"].index("--python") + 1] == "3.11"
    # Never a Microsoft Store / conda Python: a venv on those cannot start.
    assert seen["env"]["UV_PYTHON_PREFERENCE"] == "only-managed"


def test_missing_uv_is_downloaded_where_find_uv_looks(monkeypatch, tmp_path) -> None:
    import io
    import zipfile

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("uv-x86_64-pc-windows-msvc/uv.exe", b"fake uv")
        z.writestr("uv-x86_64-pc-windows-msvc/uvx.exe", b"not this one")
    asked = []

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout):
        asked.append(url)
        return _Response(archive.getvalue())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(_setup.os, "name", "nt")
    monkeypatch.setattr(_setup, "UV_HOME", tmp_path / "bin")
    monkeypatch.setattr(_setup.shutil, "which", lambda _name: None)
    monkeypatch.setattr(_setup.Path, "home", lambda: tmp_path / "home")

    path = _setup.download_uv(lambda _line: None)

    assert Path(path).read_bytes() == b"fake uv"
    assert f"/{_setup.UV_VERSION}/uv-" in asked[0]  # the pinned release, not "latest"
    assert _setup.find_uv() == path


def test_a_new_gee_key_is_saved_and_the_old_one_kept(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(_setup, "DEFAULT_GEE_KEY", tmp_path / ".scrutech" / "gee_key.json")
    assert _setup.save_gee_key('{"a": 1}') == _setup.DEFAULT_GEE_KEY
    assert _setup.save_gee_key('{"a": 1}') is None  # same key: nothing to do
    _setup.save_gee_key('{"b": 2}')
    assert _setup.DEFAULT_GEE_KEY.read_text(encoding="utf-8") == '{"b": 2}'
    assert (tmp_path / ".scrutech" / "gee_key.json.bak").read_text(encoding="utf-8") == '{"a": 1}'


def test_geoai_is_an_explicit_extra(monkeypatch, tmp_path) -> None:
    seen = []

    class _Proc:
        stdout: list[str] = []

        def __init__(self, cmd, **_kwargs):
            seen.append(cmd)

        def wait(self) -> int:
            return 0

    monkeypatch.setattr(_setup.subprocess, "Popen", _Proc)
    _setup.install_env("uv", tmp_path, lambda _l: None, lambda: False)
    _setup.install_env("uv", tmp_path, lambda _l: None, lambda: False, geoai=True)
    assert "--extra" not in seen[0] and seen[1][-2:] == ["--extra", "geoai"]


def test_the_message_bar_shows_the_useful_line_of_a_failed_setup() -> None:
    todo = "QGIS 4.2\n[OK] Internet\n[À FAIRE] Il manque des modules (h3).\nfin\n"
    assert _setup.install_problem(todo) == "[À FAIRE] Il manque des modules (h3)."
    crash = "Commande : uv sync\nLe programme uv ne se lance pas (uv.exe) : introuvable.\n"
    assert _setup.install_problem(crash).startswith("Le programme uv ne se lance pas")
    # A multi-line error: its headline, not its last numbered step or indented command.
    steps = _setup.UV_MISSING.format(error="proxy")
    assert _setup.install_problem("Commande : x\n" + steps).startswith("Le programme « uv »")
