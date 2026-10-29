"""Detected native llama.cpp runtime identity.

A configured release string is not proof of what is installed. This module asks the
actual ``llama-server`` executable for its version so the launcher, the UI, and the
diagnostics page can report the runtime that is really on disk instead of a constant
copied from a build script.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import shutil
import subprocess
import sys

# Single authoritative statement of the llama.cpp build this project is developed and
# verified against. ``setup.py`` imports these so the installer and the UI cannot
# drift apart. llama.cpp tags binaries by nightly build (b####); the semantic release
# ``v0.8.0`` is that same build (its release asset ``nightly-tag.txt`` names it).
EXPECTED_LLAMA_CPP_SEMVER = "v0.8.0"
EXPECTED_LLAMA_CPP_BUILD = "b11960"

# ``llama-server --version`` prints e.g.
#   version: 0.8.0-dev (build 11960, commit 8642541b2)
#   built with Clang 20.1.8 for Windows x86_64
_VERSION_RE = re.compile(
    r"version:\s*(?P<version>\S+)\s*\(build\s*(?P<build>\d+),\s*commit\s*(?P<commit>[0-9a-fA-F]+)\)"
)
_MAX_VERSION_OUTPUT = 4096


@dataclass(frozen=True)
class RuntimeVersion:
    """Parsed ``llama-server --version`` output."""

    path: Path
    version: str
    build: str
    commit: str
    raw: str

    @property
    def label(self) -> str:
        """Return a compact human-readable identifier, e.g. ``0.8.0-dev (build 11960)``."""
        return f"{self.version} (build {self.build})"


def default_llama_server_path(project_root: Path | None = None) -> Path:
    """Return the project-local llama-server executable path.

    Args:
        project_root: Repository root; defaults to the parent of this package.

    Returns:
        Path to ``tools/llama-server/llama-server[.exe]``.
    """
    root = project_root or Path(__file__).resolve().parent.parent
    exe = "llama-server.exe" if sys.platform == "win32" else "llama-server"
    return root / "tools" / "llama-server" / exe


def find_llama_server_binary(project_root: Path | None = None) -> Path | None:
    """Locate llama-server on PATH first, then in the project's ``tools/`` directory.

    Args:
        project_root: Repository root used for the local fallback.

    Returns:
        The executable path, or None when no runtime is installed.
    """
    on_path = shutil.which("llama-server")
    if on_path:
        return Path(on_path)
    local = default_llama_server_path(project_root)
    return local if local.exists() else None


def parse_version_output(raw: str) -> tuple[str, str, str] | None:
    """Parse ``llama-server --version`` output.

    Args:
        raw: Combined stdout/stderr of the version command.

    Returns:
        ``(version, build, commit)``, or None when the output is not recognisable.
    """
    match = _VERSION_RE.search(raw or "")
    if not match:
        return None
    return match.group("version"), match.group("build"), match.group("commit")


def detect_runtime_version(
    exe_path: Path | None = None,
    project_root: Path | None = None,
    timeout: float = 5.0,
) -> RuntimeVersion | None:
    """Run the installed llama-server binary and report its real version.

    Args:
        exe_path: Explicit executable path; otherwise the binary is discovered.
        project_root: Repository root used for the local fallback.
        timeout: Seconds to wait for the version command.

    Returns:
        RuntimeVersion when the binary runs and reports a parsable version, else None.
    """
    exe = exe_path or find_llama_server_binary(project_root)
    if exe is None or not Path(exe).exists():
        return None
    try:
        completed = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    raw = f"{completed.stdout or ''}{completed.stderr or ''}".strip()[:_MAX_VERSION_OUTPUT]
    parsed = parse_version_output(raw)
    if parsed is None:
        return None
    version, build, commit = parsed
    return RuntimeVersion(path=Path(exe), version=version, build=build, commit=commit, raw=raw)


@lru_cache(maxsize=8)
def cached_runtime_version(project_root: Path | None = None) -> RuntimeVersion | None:
    """Return the detected runtime version, cached for the life of the process.

    Streamlit reruns the whole script on every interaction; probing the binary each
    time would fork a process per widget click. The cache is keyed by the resolved
    root path so tests and diagnostics can still ask for a specific install.

    Args:
        project_root: Repository root used to locate the bundled binary.

    Returns:
        RuntimeVersion when the binary runs and reports a version, else None.
    """
    return detect_runtime_version(project_root=project_root)


def runtime_status_line(project_root: Path | None = None) -> str:
    """Describe the installed runtime relative to the expected build.

    Args:
        project_root: Repository root used to locate the bundled binary.

    Returns:
        A one-line status string for the UI and the launcher banner.
    """
    detected = cached_runtime_version(project_root)
    expected = f"{EXPECTED_LLAMA_CPP_SEMVER} ({EXPECTED_LLAMA_CPP_BUILD})"
    if detected is None:
        return f"llama-server not detected (expected {expected})"
    # ``--version`` reports the bare build number (``build 11960``) while release tags
    # carry a ``b`` prefix (``b11960``); compare the numeric identity only.
    if detected.build.lstrip("b") == EXPECTED_LLAMA_CPP_BUILD.lstrip("b"):
        return f"llama.cpp {detected.version} (build {detected.build}) - matches expected {expected}"
    return f"llama.cpp {detected.version} (build {detected.build}) - expected {expected}"
