import sys
from unittest.mock import MagicMock, patch

import pytest

import setup as setup_mod


def test_detect_nvidia_gpu_success():
    """Verify detect_nvidia_gpu returns True when nvidia-smi succeeds."""
    mock_res = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_res):
        assert setup_mod.detect_nvidia_gpu() is True


def test_detect_nvidia_gpu_failure():
    """Verify detect_nvidia_gpu returns False when nvidia-smi fails or throws."""
    mock_res = MagicMock(returncode=1)
    with patch("subprocess.run", return_value=mock_res):
        assert setup_mod.detect_nvidia_gpu() is False

    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert setup_mod.detect_nvidia_gpu() is False


def test_get_local_llama_server_path(tmp_path):
    """Verify get_local_llama_server_path respects target tools directory."""
    path = setup_mod.get_local_llama_server_path(tmp_path)
    expected_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    assert path == tmp_path / expected_name


def test_setup_llama_server_already_operational(tmp_path, capsys):
    """Verify setup_llama_server skips download if binary exists and --version succeeds."""
    exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    fake_exe = tmp_path / exe_name
    fake_exe.write_text("binary", encoding="utf-8")

    mock_run = MagicMock(returncode=0)
    with patch("subprocess.run", return_value=mock_run):
        ok = setup_mod.setup_llama_server(tools_dir=tmp_path, force=False)
        assert ok is True
        captured = capsys.readouterr()
        assert "already installed and operational" in captured.out


def test_setup_llama_server_downloads_when_missing(tmp_path):
    """Verify setup_llama_server invokes download_and_extract_archive and verifies binary."""
    exe_name = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    fake_exe = tmp_path / exe_name

    def fake_download(*args, **kwargs):
        fake_exe.write_text("dummy", encoding="utf-8")
        return True

    mock_run = MagicMock(returncode=0)
    with (
        patch("setup.detect_nvidia_gpu", return_value=False),
        patch("setup.download_and_extract_archive", side_effect=fake_download),
        patch("subprocess.run", return_value=mock_run),
    ):
        ok = setup_mod.setup_llama_server(tools_dir=tmp_path, force=True, cpu_only=True)
        assert ok is True


def test_run_full_setup_orchestration(tmp_path):
    """Verify run_full_setup calls ensure_project_directories, install_dependencies, download_all_models, and setup_llama_server."""
    with (
        patch("setup.ensure_project_directories") as mock_dirs,
        patch("setup.install_dependencies", return_value=True) as mock_deps,
        patch("setup.download_all_models", return_value=True) as mock_models,
        patch("setup.setup_llama_server", return_value=True) as mock_llama,
        patch("subprocess.run"),
    ):
        rc = setup_mod.run_full_setup(skip_vlm=True, force_models=False, skip_llama=False)
        assert rc == 0
        mock_dirs.assert_called_once()
        mock_deps.assert_called_once()
        mock_models.assert_called_once()
        mock_llama.assert_called_once()


def _write_tar(path, entries):
    """Create a tar.gz from (name, kind, payload) entries for extraction tests."""
    import io
    import tarfile

    with tarfile.open(path, "w:gz") as tf:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tf.addfile(info)
            elif kind == "sym":
                info.type = tarfile.SYMTYPE
                info.linkname = payload
                info.mode = 0o777
                tf.addfile(info)
            elif kind == "lnk":
                info.type = tarfile.LNKTYPE
                info.linkname = payload
                info.mode = 0o644
                tf.addfile(info)
            else:
                data = payload.encode("utf-8")
                info.size = len(data)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))


def test_safe_extract_archive_strips_root_and_restores_links(tmp_path):
    """Verify strip_root flattens the archive and recreates contained soname links."""
    archive = tmp_path / "llama.tar.gz"
    _write_tar(
        archive,
        [
            ("pkg-b1/", "dir", ""),
            ("pkg-b1/llama-server", "file", "binary"),
            ("pkg-b1/libllama-common.so.0.8.0", "file", "lib"),
            ("pkg-b1/libllama-common.so.0", "sym", "libllama-common.so.0.8.0"),
            ("pkg-b1/libllama-common.so", "sym", "libllama-common.so.0"),
            ("pkg-b1/hardlink.so", "lnk", "pkg-b1/libllama-common.so.0.8.0"),
        ],
    )
    dest = tmp_path / "out"
    setup_mod.safe_extract_archive(archive, dest, strip_root=True)

    assert (dest / "llama-server").read_text(encoding="utf-8") == "binary"
    assert not (dest / "pkg-b1").exists()
    assert (dest / "libllama-common.so").resolve() == (dest / "libllama-common.so.0.8.0").resolve()
    assert (dest / "hardlink.so").read_text(encoding="utf-8") == "lib"


def test_safe_extract_archive_reextracts_over_existing_links(tmp_path):
    """Verify re-extraction replaces stale links instead of following them."""
    archive = tmp_path / "pkg.tar.gz"
    _write_tar(
        archive,
        [
            ("pkg/", "dir", ""),
            ("pkg/libfoo.so.1.0", "file", "lib"),
            ("pkg/libfoo.so.1", "sym", "libfoo.so.1.0"),
            ("pkg/libfoo.so", "sym", "libfoo.so.1"),
        ],
    )
    dest = tmp_path / "out"
    setup_mod.safe_extract_archive(archive, dest, strip_root=True)
    setup_mod.safe_extract_archive(archive, dest, strip_root=True)

    assert (dest / "libfoo.so.1.0").is_file()
    assert (dest / "libfoo.so").resolve() == (dest / "libfoo.so.1.0").resolve()


def test_safe_extract_archive_zip_stays_flat(tmp_path):
    """Verify the zip path (Windows builds) still extracts without flattening."""
    import zipfile

    archive = tmp_path / "llama-win.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("llama-server.exe", "bin")
        zf.writestr("ggml.dll", "dll")
    dest = tmp_path / "out"
    setup_mod.safe_extract_archive(archive, dest)
    assert (dest / "llama-server.exe").read_text(encoding="utf-8") == "bin"
    assert (dest / "ggml.dll").is_file()


def test_safe_extract_archive_rejects_escaping_members(tmp_path, capsys):
    """Verify escaping symlinks are skipped and traversal members are rejected."""
    archive = tmp_path / "evil.tar.gz"
    _write_tar(
        archive,
        [
            ("pkg/", "dir", ""),
            ("pkg/libgood.so.1", "file", "good"),
            ("pkg/libgood.so", "sym", "libgood.so.1"),
            ("pkg/evil", "sym", "../../etc/passwd"),
            ("pkg/evil-hard", "lnk", "../../etc/passwd"),
            ("pkg/../escape.txt", "file", "escaped"),
        ],
    )
    dest = tmp_path / "out"
    with pytest.raises(ValueError, match="escapes destination"):
        setup_mod.safe_extract_archive(archive, dest, strip_root=True)
    assert not (dest / "evil").exists()
    assert not (dest / "evil-hard").exists()
    assert not (tmp_path / "escape.txt").exists()
    assert "Skipping unsafe archive link" in capsys.readouterr().out
