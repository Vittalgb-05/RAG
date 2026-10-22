import hashlib
import io
import re

import pytest

import setup as setup_mod


class FakeResponse(io.BytesIO):
    """Minimal urllib response stand-in with a Content-Length header."""

    def __init__(self, payload: bytes) -> None:
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


def test_model_registry_pins_sha256_for_every_artifact():
    """Every downloadable model must carry a pinned 64-character SHA-256 digest."""
    assert setup_mod.MODEL_REGISTRY
    for model in setup_mod.MODEL_REGISTRY:
        digest = model.get("sha256")
        assert isinstance(digest, str)
        assert re.fullmatch(r"[0-9a-f]{64}", digest), model["name"]


def test_llama_archive_checksums_cover_all_download_paths():
    """All llama-server archives referenced by the installer must have pinned digests."""
    release = setup_mod.LLAMA_SERVER_RELEASE
    required = [
        f"llama-{release}-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
        f"llama-{release}-bin-win-cpu-x64.zip",
        f"llama-{release}-bin-ubuntu-x64.tar.gz",
        f"llama-{release}-bin-ubuntu-cuda-12.8-x64.tar.gz",
    ]
    for name in required:
        assert re.fullmatch(r"[0-9a-f]{64}", setup_mod.LLAMA_ARCHIVE_SHA256.get(name, "")), name


def test_file_sha256_matches_hashlib(tmp_path):
    """file_sha256 must produce the same digest as a one-shot hash."""
    target = tmp_path / "payload.bin"
    payload = b"grounded evidence" * 4096
    target.write_bytes(payload)
    assert setup_mod.file_sha256(target) == hashlib.sha256(payload).hexdigest()


def test_existing_file_with_matching_hash_is_not_downloaded(tmp_path, monkeypatch):
    """A pre-existing artifact whose digest matches must be reused without network access."""
    payload = b"verified model bytes"
    target = tmp_path / "model.gguf"
    target.write_bytes(payload)

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network access is not expected")

    monkeypatch.setattr(setup_mod.urllib.request, "urlopen", fail_urlopen)
    ok = setup_mod.download_file_with_progress(
        urls=["https://example.invalid/model.gguf"],
        dest_path=target,
        min_size_bytes=1,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert ok is True
    assert target.read_bytes() == payload


def test_existing_file_with_wrong_hash_is_replaced(tmp_path, monkeypatch):
    """A stale local artifact that fails checksum verification must be re-downloaded."""
    payload = b"replacement model bytes"
    target = tmp_path / "model.gguf"
    target.write_bytes(b"stale bytes")

    monkeypatch.setattr(
        setup_mod.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(payload),
    )
    ok = setup_mod.download_file_with_progress(
        urls=["https://example.invalid/model.gguf"],
        dest_path=target,
        min_size_bytes=1,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
    )
    assert ok is True
    assert target.read_bytes() == payload


def test_download_rejects_checksum_mismatch(tmp_path, monkeypatch):
    """A download whose bytes do not match the pinned digest must be discarded."""
    target = tmp_path / "model.gguf"
    monkeypatch.setattr(
        setup_mod.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(b"tampered payload"),
    )
    ok = setup_mod.download_file_with_progress(
        urls=["https://example.invalid/model.gguf"],
        dest_path=target,
        min_size_bytes=1,
        expected_sha256="0" * 64,
    )
    assert ok is False
    assert not target.exists()
    assert not target.with_suffix(".tmp").exists()


def test_require_checksums_fails_closed_without_pinned_digest(tmp_path, monkeypatch):
    """RAG_REQUIRE_CHECKSUMS must refuse unpinned downloads before touching the network."""
    monkeypatch.setenv("RAG_REQUIRE_CHECKSUMS", "1")

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("network access is not expected")

    monkeypatch.setattr(setup_mod.urllib.request, "urlopen", fail_urlopen)
    ok = setup_mod.download_file_with_progress(
        urls=["https://example.invalid/model.gguf"],
        dest_path=tmp_path / "model.gguf",
        min_size_bytes=1,
    )
    assert ok is False


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off"])
def test_require_checksums_is_disabled_by_default(monkeypatch, value):
    """Only truthy RAG_REQUIRE_CHECKSUMS values enable fail-closed enforcement."""
    monkeypatch.setenv("RAG_REQUIRE_CHECKSUMS", value)
    assert setup_mod.require_pinned_checksums() is False
