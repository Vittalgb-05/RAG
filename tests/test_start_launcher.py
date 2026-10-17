"""Unit tests for start.py application launcher."""

import sys
from unittest.mock import MagicMock, patch
import urllib.error


import start


def test_banner_prints(capsys):
    """Verify startup banner prints system name and features."""
    start.print_banner()
    captured = capsys.readouterr()
    assert "Local-First Multimodal PDF Intelligence System" in captured.out
    assert "Docling" in captured.out


def test_python_version_check():
    """Verify python version check against simulated version info."""
    with patch.object(sys, "version_info", (3, 11, 2)):
        assert start.check_python_version() is True

    with patch.object(sys, "version_info", (3, 10, 8)):
        assert start.check_python_version() is False


def test_ensure_directories(tmp_path):
    """Verify ensure_directories creates required folders."""
    with patch("start.REPO_ROOT", tmp_path):
        start.ensure_directories()
        assert (tmp_path / "data").exists()
        assert (tmp_path / ".cache").exists()
        assert (tmp_path / "models").exists()


def test_check_llama_server_healthy(capsys):
    """Verify check_llama_server reports detected status when HTTP 200 returned."""
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b'{"status":"ok"}'
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        start.check_llama_server(host="127.0.0.1", port=8080)
        captured = capsys.readouterr()
        assert "Local llama-server detected" in captured.out


def test_check_llama_server_503(capsys):
    """Verify check_llama_server reports model loading when HTTP 503 returned."""
    he = urllib.error.HTTPError("http://127.0.0.1:8080/health", 503, "Loading", {}, None)
    with patch("urllib.request.urlopen", side_effect=he):
        start.check_llama_server(host="127.0.0.1", port=8080)
        captured = capsys.readouterr()
        assert "currently loading models" in captured.out


def test_check_llama_server_offline(capsys):
    """Verify check_llama_server reports offline instructions when unreachable."""
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        start.check_llama_server(host="127.0.0.1", port=8080)
        captured = capsys.readouterr()
        assert "Local llama-server not detected" in captured.out


def test_launch_streamlit_invokes_subprocess():
    """Verify launch_streamlit constructs correct CLI invocation."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        rc = start.launch_streamlit(port=8501, host="localhost", headless=True)
        assert rc == 0
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "streamlit" in cmd
        assert "--server.port=8501" in cmd
        assert "--server.address=localhost" in cmd
        assert "--server.headless=true" in cmd
        assert "--browser.gatherUsageStats=false" in cmd


def test_main_cli_args_parsing():
    """Verify main() parses arguments and executes pre-flight sequence."""
    test_args = ["start.py", "--port", "9000", "--host", "127.0.0.1", "--headless"]
    with patch.object(sys, "argv", test_args):
        with patch("start.check_python_version", return_value=True):
            with patch("start.ensure_directories"):
                with patch("start.check_llama_server"):
                    with patch("start.launch_streamlit", return_value=0) as mock_launch:
                        rc = start.main()
                        assert rc == 0
                        mock_launch.assert_called_once_with(port=9000, host="127.0.0.1", headless=True)
