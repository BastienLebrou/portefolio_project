"""ensure_model TOFU pinning — offline, no real download (see geoai_segment docstring)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vegevigie import geoai_segment as gs


def _fake_download(monkeypatch: pytest.MonkeyPatch, content: bytes) -> None:
    """Replace urlopen with a stub serving ``content`` — no network in tests."""

    class _FakeResponse:
        headers = {"Content-Length": str(len(content))}

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, _size: int = -1) -> bytes:
            nonlocal content
            out, content = content, b""
            return out

    monkeypatch.setattr(gs.urllib.request, "urlopen", lambda *_a, **_kw: _FakeResponse())


def test_ensure_model_downloads_and_pins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_download(monkeypatch, b"fake-weights-bytes")

    path = gs.ensure_model(cache_dir=tmp_path)

    assert path.exists()
    assert path.with_suffix(path.suffix + ".sha256").exists()
    assert gs._sha256(path) == path.with_suffix(path.suffix + ".sha256").read_text().strip()


def test_ensure_model_reuses_cache_without_redownloading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_download(monkeypatch, b"fake-weights-bytes")
    gs.ensure_model(cache_dir=tmp_path)

    def _boom(*_a, **_kw):
        raise AssertionError("should not re-download when the cache is valid")

    monkeypatch.setattr(gs.urllib.request, "urlopen", _boom)

    path = gs.ensure_model(cache_dir=tmp_path)
    assert path.exists()


def test_ensure_model_rejects_a_tampered_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_download(monkeypatch, b"fake-weights-bytes")
    path = gs.ensure_model(cache_dir=tmp_path)
    path.write_bytes(b"tampered")  # file changed after the pin was written

    with pytest.raises(RuntimeError, match="checksum"):
        gs.ensure_model(cache_dir=tmp_path)
