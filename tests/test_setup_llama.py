import sys
from unittest.mock import MagicMock, patch

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
    with patch("setup.detect_nvidia_gpu", return_value=False):
        with patch("setup.download_and_extract_archive", side_effect=fake_download):
            with patch("subprocess.run", return_value=mock_run):
                ok = setup_mod.setup_llama_server(tools_dir=tmp_path, force=True, cpu_only=True)
                assert ok is True


def test_run_full_setup_orchestration(tmp_path):
    """Verify run_full_setup calls ensure_project_directories, install_dependencies, download_all_models, and setup_llama_server."""
    with patch("setup.ensure_project_directories") as mock_dirs:
        with patch("setup.install_dependencies", return_value=True) as mock_deps:
            with patch("setup.download_all_models", return_value=True) as mock_models:
                with patch("setup.setup_llama_server", return_value=True) as mock_llama:
                    with patch("subprocess.run"):
                        rc = setup_mod.run_full_setup(skip_vlm=True, force_models=False, skip_llama=False)
                        assert rc == 0
                        mock_dirs.assert_called_once()
                        mock_deps.assert_called_once()
                        mock_models.assert_called_once()
                        mock_llama.assert_called_once()
