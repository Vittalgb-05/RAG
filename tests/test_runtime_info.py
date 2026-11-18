"""Runtime detection, expected-build pinning, and GGUF pair compatibility tests."""

import struct
from pathlib import Path
import subprocess

import pytest

import setup as setup_mod
from core import runtime_info
from core.model_identity import read_gguf_metadata, verify_local_model_pair

REAL_VERSION_OUTPUT = "version: 0.8.0-dev (build 11960, commit 8642541b2)\nbuilt with Clang 20.1.8 for Windows x86_64\n"


# ---------------------------------------------------------------------------
# Version parsing and detection
# ---------------------------------------------------------------------------


def test_parse_version_output_reads_version_build_and_commit():
    """The parser must extract the three facts llama-server prints."""
    assert runtime_info.parse_version_output(REAL_VERSION_OUTPUT) == ("0.8.0-dev", "11960", "8642541b2")


def test_parse_version_output_rejects_unrecognised_output():
    """Unrelated output must not be reported as a detected version."""
    assert runtime_info.parse_version_output("llama-server: command not found") is None
    assert runtime_info.parse_version_output("") is None


def test_detect_runtime_version_returns_none_for_missing_binary(tmp_path):
    """A missing executable is reported as undetected, not as a version."""
    assert runtime_info.detect_runtime_version(tmp_path / "llama-server.exe") is None


def test_detect_runtime_version_parses_real_subprocess_output(tmp_path, monkeypatch):
    """Detection reads the executable's own output rather than a configured constant."""
    exe = tmp_path / ("llama-server.exe" if runtime_info.sys.platform == "win32" else "llama-server")
    exe.write_text("stub", encoding="utf-8")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=["llama-server", "--version"], returncode=0, stdout=REAL_VERSION_OUTPUT)

    monkeypatch.setattr(runtime_info.subprocess, "run", fake_run)
    detected = runtime_info.detect_runtime_version(exe)
    assert detected is not None
    assert detected.version == "0.8.0-dev"
    assert detected.build == "11960"
    assert detected.commit == "8642541b2"
    assert detected.label == "0.8.0-dev (build 11960)"


def test_detect_runtime_version_survives_execution_failure(tmp_path, monkeypatch):
    """An executable that cannot run must not raise out of the detection helper."""
    exe = tmp_path / "llama-server"
    exe.write_text("stub", encoding="utf-8")

    def fake_run(*args, **kwargs):
        raise OSError("cannot execute")

    monkeypatch.setattr(runtime_info.subprocess, "run", fake_run)
    assert runtime_info.detect_runtime_version(exe) is None


def test_runtime_status_line_reports_match_and_mismatch(monkeypatch):
    """The status line distinguishes the expected build from a stale install."""
    matching = runtime_info.RuntimeVersion(
        path=Path("llama-server.exe"), version="0.8.0-dev", build="11960", commit="8642541b2", raw=""
    )
    monkeypatch.setattr(runtime_info, "cached_runtime_version", lambda _root=None: matching)
    assert "matches expected" in runtime_info.runtime_status_line()

    stale = runtime_info.RuntimeVersion(
        path=Path("llama-server.exe"), version="0.7.0-dev", build="11718", commit="547208dca", raw=""
    )
    monkeypatch.setattr(runtime_info, "cached_runtime_version", lambda _root=None: stale)
    line = runtime_info.runtime_status_line()
    assert "0.7.0-dev" in line and "expected" in line and "matches expected" not in line


def test_runtime_status_line_handles_absent_runtime(monkeypatch):
    """No installed runtime is reported explicitly."""
    monkeypatch.setattr(runtime_info, "cached_runtime_version", lambda _root=None: None)
    assert "not detected" in runtime_info.runtime_status_line()


def test_expected_runtime_pin_is_shared_with_the_installer():
    """The installer, UI, and diagnostics must reference one authoritative build pin."""
    assert setup_mod.LLAMA_SERVER_RELEASE == runtime_info.EXPECTED_LLAMA_CPP_BUILD
    assert setup_mod.LLAMA_SERVER_SEMVER == runtime_info.EXPECTED_LLAMA_CPP_SEMVER


# ---------------------------------------------------------------------------
# GGUF pair compatibility
# ---------------------------------------------------------------------------


def _write_gguf(path: Path, metadata: dict[str, str]) -> Path:
    """Write a minimal GGUF v3 container carrying only string metadata."""
    out = bytearray()
    out += b"GGUF"
    out += struct.pack("<I", 3)
    out += struct.pack("<Q", 0)  # tensor count
    out += struct.pack("<Q", len(metadata))
    for key, value in metadata.items():
        encoded_key = key.encode("utf-8")
        out += struct.pack("<Q", len(encoded_key)) + encoded_key
        out += struct.pack("<I", 8)  # string value type
        encoded_value = value.encode("utf-8")
        out += struct.pack("<Q", len(encoded_value)) + encoded_value
    path.write_bytes(bytes(out))
    return path


def test_read_gguf_metadata_parses_synthetic_container(tmp_path):
    """The identity reader must return the architecture string it was given."""
    path = _write_gguf(tmp_path / "model.gguf", {"general.architecture": "qwen35", "general.name": "Qwen3.5 2B"})
    identity = read_gguf_metadata(path)
    assert identity.architecture == "qwen35"
    assert identity.is_valid_language_model() is True


def test_qwen35_pair_is_accepted(tmp_path):
    """Qwen3.5 weights with the qwen3vl merger projector are a supported pair."""
    lm = _write_gguf(tmp_path / "lm.gguf", {"general.architecture": "qwen35", "general.name": "Qwen3.5 2B"})
    proj = _write_gguf(
        tmp_path / "mmproj.gguf",
        {"general.architecture": "clip", "clip.projector_type": "qwen3vl_merger"},
    )
    assert verify_local_model_pair(lm, proj) == []


def test_legacy_qwen2vl_pair_remains_accepted(tmp_path):
    """The previous weights stay valid so a rollback needs no code change."""
    lm = _write_gguf(tmp_path / "lm.gguf", {"general.architecture": "qwen2vl"})
    proj = _write_gguf(
        tmp_path / "mmproj.gguf",
        {"general.architecture": "clip", "clip.projector_type": "qwen2vl_merger"},
    )
    assert verify_local_model_pair(lm, proj) == []


def test_qwen35_weights_with_qwen2vl_projector_are_rejected(tmp_path):
    """A cross-generation pairing must be refused before launch."""
    lm = _write_gguf(tmp_path / "lm.gguf", {"general.architecture": "qwen35"})
    proj = _write_gguf(
        tmp_path / "mmproj.gguf",
        {"general.architecture": "clip", "clip.projector_type": "qwen2vl_merger"},
    )
    problems = verify_local_model_pair(lm, proj)
    assert any("Architecture mismatch" in problem for problem in problems)


def test_unknown_language_model_architecture_is_rejected(tmp_path):
    """An unrelated text-only checkpoint must not be presented as a VLM."""
    lm = _write_gguf(tmp_path / "lm.gguf", {"general.architecture": "llama"})
    proj = _write_gguf(
        tmp_path / "mmproj.gguf",
        {"general.architecture": "clip", "clip.projector_type": "qwen3vl_merger"},
    )
    problems = verify_local_model_pair(lm, proj)
    assert any("expected one of" in problem for problem in problems)


@pytest.mark.parametrize(
    "model_index,expected_name", [(0, "qwen3.5-2b-q4_k_m.gguf"), (1, "qwen3.5-2b-mmproj-f16.gguf")]
)
def test_model_registry_targets_qwen35_artifacts(model_index, expected_name):
    """The installer must fetch the Qwen3.5-2B weights and their projector."""
    assert setup_mod.MODEL_REGISTRY[model_index]["name"] == expected_name


def test_model_registry_urls_are_revision_pinned():
    """Every model URL must resolve an immutable revision, not a moving branch."""
    revision = setup_mod.QWEN35_GGUF_REVISION
    assert len(revision) == 40
    for model in setup_mod.MODEL_REGISTRY:
        assert all(f"/resolve/{revision}/" in url for url in model["urls"]), model["name"]
