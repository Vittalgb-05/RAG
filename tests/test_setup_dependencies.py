"""Unit tests for setup.py dependency provisioning and the venv fallback.

The reported failure was that `setup.py` reported success while the launcher
interpreter had no dependencies installed (PEP 668 rejected the system pip install
and the result was downgraded to a warning). These tests pin the new contract:
provision into an isolated environment when needed, verify imports, and never claim
success when the resulting interpreter cannot run the app.
"""

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import setup as setup_mod


# ----------------------------------------------------------------------
# Venv path resolution
# ----------------------------------------------------------------------
def test_resolve_venv_dir_defaults_to_repo_venv(monkeypatch):
    """Without overrides the environment lives at .venv in the repository root."""
    monkeypatch.delenv(setup_mod.VENV_PATH_ENV, raising=False)
    assert setup_mod.resolve_venv_dir() == (setup_mod.REPO_ROOT / ".venv").resolve()


def test_resolve_venv_dir_honours_env_override(tmp_path, monkeypatch):
    """RAG_VENV_PATH relocates the environment without touching the CLI."""
    monkeypatch.setenv(setup_mod.VENV_PATH_ENV, str(tmp_path / "env-venv"))
    assert setup_mod.resolve_venv_dir() == (tmp_path / "env-venv").resolve()


def test_resolve_venv_dir_prefers_explicit_argument(tmp_path, monkeypatch):
    """--venv-path outranks the environment variable."""
    monkeypatch.setenv(setup_mod.VENV_PATH_ENV, str(tmp_path / "env-venv"))
    assert setup_mod.resolve_venv_dir(tmp_path / "cli-venv") == (tmp_path / "cli-venv").resolve()


def test_venv_python_path_uses_platform_layout(tmp_path):
    """The interpreter path matches the venv layout for the running platform."""
    path = setup_mod.venv_python_path(tmp_path)
    if sys.platform == "win32":
        assert path == tmp_path / "Scripts" / "python.exe"
    else:
        assert path == tmp_path / "bin" / "python"


# ----------------------------------------------------------------------
# Interpreter installability (PEP 668 detection)
# ----------------------------------------------------------------------
def test_externally_managed_marker_detected(tmp_path):
    """A PEP 668 marker next to the stdlib is reported, not ignored."""
    marker = tmp_path / "EXTERNALLY-MANAGED"
    marker.write_text("", encoding="utf-8")

    with (
        patch("setup.sysconfig.get_path", return_value=str(tmp_path)),
        patch.object(setup_mod.sys, "base_prefix", str(tmp_path / "missing")),
    ):
        assert setup_mod.externally_managed_marker() == marker


def test_interpreter_accepts_pip_installs_inside_virtualenv():
    """An activated virtual environment is always installable."""
    with (
        patch.object(setup_mod.sys, "prefix", "/tmp/project-venv"),
        patch.object(setup_mod.sys, "base_prefix", "/usr"),
    ):
        assert setup_mod.interpreter_accepts_pip_installs() is True


def test_interpreter_accepts_pip_installs_rejects_pep668_host(tmp_path):
    """A system interpreter carrying EXTERNALLY-MANAGED is not installable."""
    (tmp_path / "EXTERNALLY-MANAGED").write_text("", encoding="utf-8")

    with (
        patch.object(setup_mod.sys, "prefix", "/usr"),
        patch.object(setup_mod.sys, "base_prefix", "/usr"),
        patch("setup.sysconfig.get_path", return_value=str(tmp_path)),
    ):
        assert setup_mod.interpreter_accepts_pip_installs() is False


def test_install_blocked_reason_names_pep668(tmp_path):
    """The blocking reason names the marker so the user can act on it."""
    marker = tmp_path / "EXTERNALLY-MANAGED"
    marker.write_text("", encoding="utf-8")

    with patch("setup.externally_managed_marker", return_value=marker):
        reason = setup_mod.install_blocked_reason()

    assert "PEP 668" in reason
    assert str(marker) in reason


# ----------------------------------------------------------------------
# Import probe
# ----------------------------------------------------------------------
def test_missing_modules_returns_empty_when_all_import():
    """A clean probe means the interpreter can run the app."""
    with patch("setup.subprocess.run", return_value=MagicMock(returncode=0, stdout="")):
        assert setup_mod.missing_modules("/fake/python") == []


def test_missing_modules_parses_reported_names():
    """Only names the probe actually reported are returned."""
    probe = MagicMock(returncode=1, stdout="streamlit\n")
    with patch("setup.subprocess.run", return_value=probe):
        assert setup_mod.missing_modules("/fake/python", ("streamlit", "pypdf")) == ["streamlit"]


def test_missing_modules_treats_interpreter_failure_as_all_missing():
    """If the probe cannot run at all, every module is reported missing."""
    with patch("setup.subprocess.run", side_effect=OSError("no such interpreter")):
        assert setup_mod.missing_modules("/fake/python", ("streamlit", "pypdf")) == ["streamlit", "pypdf"]


# ----------------------------------------------------------------------
# install_dependencies routing
# ----------------------------------------------------------------------
def test_install_dependencies_redirects_to_venv_on_pep668_host(tmp_path, capsys):
    """A blocked system interpreter triggers venv provisioning instead of failing."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)

    with (
        patch("setup.interpreter_accepts_pip_installs", return_value=False),
        patch("setup.install_blocked_reason", return_value="PEP 668 externally-managed environment"),
        patch("setup.provision_venv_dependencies", return_value=venv_python) as mock_provision,
    ):
        assert setup_mod.install_dependencies(venv_path=venv_dir) is True

    mock_provision.assert_called_once()
    assert mock_provision.call_args[0][0] == venv_dir
    out = capsys.readouterr().out
    assert "isolated environment" in out
    assert str(venv_dir) in out


def test_install_dependencies_uses_system_interpreter_when_installable(tmp_path):
    """An installable interpreter keeps the original behaviour."""
    req_file = tmp_path / "requirements.txt"
    req_file.write_text("streamlit==1.66.1\n", encoding="utf-8")

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.interpreter_accepts_pip_installs", return_value=True),
        patch("setup.provision_venv_dependencies") as mock_provision,
        patch("setup.missing_modules", return_value=[]),
        patch("setup.subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
    ):
        assert setup_mod.install_dependencies() is True

    mock_provision.assert_not_called()
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == [sys.executable, "-m", "pip"]
    assert str(req_file) in cmd


def test_install_dependencies_verifies_imports_after_system_pip(tmp_path, capsys):
    """A zero pip exit is not enough: the modules must actually import."""
    (tmp_path / "requirements.txt").write_text("streamlit==1.66.1\n", encoding="utf-8")

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.interpreter_accepts_pip_installs", return_value=True),
        patch("setup.missing_modules", return_value=["streamlit"]),
        patch("setup.subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        assert setup_mod.install_dependencies() is False

    assert "still fail to import" in capsys.readouterr().err


def test_install_dependencies_propagates_pip_failure(tmp_path):
    """A failing pip run in an installable interpreter is still a failure."""
    (tmp_path / "requirements.txt").write_text("streamlit==1.66.1\n", encoding="utf-8")

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.interpreter_accepts_pip_installs", return_value=True),
        patch("setup.subprocess.run", return_value=MagicMock(returncode=2)),
    ):
        assert setup_mod.install_dependencies() is False


# ----------------------------------------------------------------------
# provision_venv_dependencies
# ----------------------------------------------------------------------
def test_provision_venv_dependencies_reuses_usable_environment(tmp_path, capsys):
    """An environment that already imports everything is not re-installed."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    with (
        patch("setup.missing_modules", return_value=[]),
        patch("setup.subprocess.run") as mock_run,
    ):
        assert setup_mod.provision_venv_dependencies(venv_dir) == venv_python

    mock_run.assert_not_called()
    assert "Reusing isolated environment" in capsys.readouterr().out


def test_provision_venv_dependencies_creates_environment_and_installs(tmp_path):
    """On a fresh checkout the venv is created, requirements installed, then verified."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)
    recorded: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        recorded.append(list(cmd))
        if cmd[:3] == [sys.executable, "-m", "venv"]:
            venv_python.parent.mkdir(parents=True, exist_ok=True)
            venv_python.write_text("", encoding="utf-8")
        return MagicMock(returncode=0)

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.subprocess.run", side_effect=fake_run),
        patch("setup.missing_modules", return_value=[]),
    ):
        assert setup_mod.provision_venv_dependencies(venv_dir, use_lockfile=True) == venv_python

    assert recorded[0][:3] == [sys.executable, "-m", "venv"]
    install_cmds = recorded[1:]
    assert install_cmds[0][:5] == [str(venv_python), "-m", "pip", "install", "-r"]
    assert install_cmds[0][5].endswith("requirements-lock.txt")
    assert install_cmds[1] == [str(venv_python), "-m", "pip", "install", "-e", "."]


def test_provision_venv_dependencies_fails_when_streamlit_still_missing(tmp_path):
    """Installing without a working streamlit import is a failure, not a success."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.missing_modules", return_value=["streamlit"]),
        patch("setup.subprocess.run", return_value=MagicMock(returncode=0)),
    ):
        assert setup_mod.provision_venv_dependencies(venv_dir) is None


def test_provision_venv_dependencies_fails_when_pip_fails(tmp_path):
    """A non-zero pip exit inside the venv aborts provisioning."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    with (
        patch("setup.REPO_ROOT", tmp_path),
        patch("setup.missing_modules", return_value=["streamlit"]),
        patch("setup.subprocess.run", return_value=MagicMock(returncode=1)),
    ):
        assert setup_mod.provision_venv_dependencies(venv_dir) is None


# ----------------------------------------------------------------------
# run_full_setup exit code
# ----------------------------------------------------------------------
def test_run_full_setup_fails_loudly_when_dependencies_fail(capsys):
    """Dependency failure must abort setup with a non-zero code, not 'Setup Complete'."""
    with (
        patch("setup.ensure_project_directories"),
        patch("setup.install_dependencies", return_value=False),
        patch("setup.download_all_models") as mock_models,
        patch("setup.setup_llama_server") as mock_llama,
    ):
        rc = setup_mod.run_full_setup()

    assert rc == 1
    mock_models.assert_not_called()
    mock_llama.assert_not_called()
    captured = capsys.readouterr()
    assert "Setup failed" in captured.err
    assert "Setup Complete" not in captured.out


def test_run_full_setup_prints_venv_launch_command(tmp_path, capsys):
    """Success prints the exact launch command for the provisioned interpreter."""
    venv_python = setup_mod.venv_python_path(tmp_path / ".venv")

    with (
        patch("setup.ensure_project_directories"),
        patch("setup.install_dependencies", return_value=True),
        patch("setup.download_all_models"),
        patch("setup.setup_llama_server"),
        patch("setup.app_python_executable", return_value=venv_python),
    ):
        rc = setup_mod.run_full_setup()

    assert rc == 0
    out = capsys.readouterr().out
    assert "Setup Complete" in out
    assert f"{venv_python} start.py --start-llama" in out


def test_run_full_setup_skips_editable_install_when_venv_used(tmp_path):
    """The venv path already installs the package, so setup must not install it twice."""
    venv_python = setup_mod.venv_python_path(tmp_path / ".venv")

    with (
        patch("setup.ensure_project_directories"),
        patch("setup.install_dependencies", return_value=True),
        patch("setup.download_all_models"),
        patch("setup.setup_llama_server"),
        patch("setup.app_python_executable", return_value=venv_python),
        patch("setup.subprocess.run") as mock_run,
    ):
        assert setup_mod.run_full_setup() == 0

    mock_run.assert_not_called()


# ----------------------------------------------------------------------
# --llama-server pre-flight
# ----------------------------------------------------------------------
def test_llama_only_preflight_reports_ready(tmp_path, capsys):
    """A ready environment gets the exact launch command."""
    venv_python = setup_mod.venv_python_path(tmp_path / ".venv")

    with (
        patch("setup.app_python_executable", return_value=venv_python),
        patch("setup.missing_modules", return_value=[]),
    ):
        assert setup_mod.report_dependency_preflight() is True

    out = capsys.readouterr().out
    assert "dependencies ready" in out
    assert f"{venv_python} start.py --start-llama" in out


def test_llama_only_preflight_warns_and_names_install_command(tmp_path, capsys):
    """Missing deps after --llama-server are explicit and actionable."""
    venv_dir = tmp_path / ".venv"

    with (
        patch("setup.app_python_executable", return_value=Path("/usr/bin/python3")),
        patch("setup.missing_modules", return_value=["streamlit"]),
        patch("setup.resolve_venv_dir", return_value=venv_dir),
    ):
        assert setup_mod.report_dependency_preflight(venv_path=venv_dir) is False

    out = capsys.readouterr().out
    assert "NOT installed" in out
    assert "streamlit" in out
    assert "/usr/bin/python3" in out
    assert "python3 setup.py" in out
    assert f"{setup_mod.venv_python_path(venv_dir)} start.py --start-llama" in out


def test_app_python_executable_prefers_usable_venv_on_blocked_host(tmp_path):
    """On a PEP 668 host the launcher interpreter is the venv, when it is ready."""
    venv_dir = tmp_path / ".venv"
    venv_python = setup_mod.venv_python_path(venv_dir)
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("", encoding="utf-8")

    with (
        patch("setup.interpreter_accepts_pip_installs", return_value=False),
        patch("setup.resolve_venv_dir", return_value=venv_dir),
        patch("setup.missing_modules", return_value=[]),
    ):
        assert setup_mod.app_python_executable() == venv_python


def test_app_python_executable_falls_back_to_running_interpreter(tmp_path):
    """An unusable venv must not be advertised as the launcher interpreter."""
    with (
        patch("setup.interpreter_accepts_pip_installs", return_value=False),
        patch("setup.resolve_venv_dir", return_value=tmp_path / ".venv"),
    ):
        assert setup_mod.app_python_executable() == Path(sys.executable)
