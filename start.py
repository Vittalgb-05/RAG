"""One-command application launcher for Local-First Multimodal PDF Intelligence System.

Usage:
    python start.py
    python start.py --port 8501 --host localhost
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import contextlib
import sys
import time
import urllib.error
import urllib.request

# Ensure UTF-8 stdout/stderr across Windows consoles (cp1252/cp437)
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

REPO_ROOT = Path(__file__).resolve().parent

# Modules main.py resolves at import time. Checking them before spawning anything is
# what turns "llama-server is up but Streamlit cannot import" into an immediate,
# actionable exit.
REQUIRED_MODULES: tuple[str, ...] = (
    "streamlit",
    "dotenv",
    "pydantic",
    "httpx",
    "langchain_text_splitters",
    "pypdf",
)

# Must match setup.py's provisioning default so the remediation hint is accurate.
DEFAULT_VENV_DIRNAME = ".venv"
VENV_PATH_ENV = "RAG_VENV_PATH"

# Host values that keep the single-user Streamlit UI reachable only from this machine.
_LOOPBACK_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}
_NON_LOOPBACK_OPT_IN_ENV = "RAG_ALLOW_NON_LOOPBACK"


def is_loopback_host(host: str) -> bool:
    """Return True when *host* binds only the local loopback interface."""
    normalized = (host or "").strip().lower().strip("[]")
    if normalized in _LOOPBACK_HOSTNAMES:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def non_loopback_opt_in() -> bool:
    """Return True when the operator explicitly opted into a non-loopback bind."""
    return os.environ.get(_NON_LOOPBACK_OPT_IN_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def refuse_unsafe_bind(host: str, allow_non_loopback: bool = False) -> bool:
    """Refuse a non-loopback UI bind unless the operator explicitly opted in.

    The application has no authentication layer: every indexed document and the
    cloud API-key settings page are readable by anyone who can reach the port.
    It is therefore designed for a single trusted user on one machine.

    Returns:
        True when the bind is allowed, False when it must be refused.
    """
    if is_loopback_host(host):
        return True

    if allow_non_loopback or non_loopback_opt_in():
        print(
            f"WARNING: Binding Streamlit to non-loopback host '{host}'.\n"
            "   This application has NO authentication: anyone who can reach this\n"
            "   port can read every indexed document and the cloud API-key page.\n"
            "   Only do this on a trusted, isolated network.",
            file=sys.stderr,
        )
        return True

    print(
        f"❌ Refusing to bind Streamlit to non-loopback host '{host}'.\n"
        "   This application is single-user and has NO authentication: any host\n"
        "   that can reach this port can read every indexed document and the\n"
        "   cloud API-key settings page.\n"
        "   Use --host 127.0.0.1 (default) or, if you accept the risk, re-run with\n"
        f"   --allow-non-loopback or set {_NON_LOOPBACK_OPT_IN_ENV}=1.",
        file=sys.stderr,
    )
    return False


def print_banner() -> None:
    """Print ASCII startup banner with the detected native runtime version."""
    print("=" * 68)
    print("  📄 Local-First Multimodal PDF Intelligence System")
    print("  Hybrid Search • RapidOCR • Docling • Qwen3.5-2B • Verifiable Citations")
    print(f"  Runtime: {runtime_status_label()}")
    print("=" * 68)


def check_python_version() -> bool:
    """Verify minimum Python 3.11 requirement."""
    if sys.version_info < (3, 11):
        print(f"❌ Error: Python 3.11+ required. Detected: {sys.version.split()[0]}", file=sys.stderr)
        return False
    return True


def repo_venv_dir() -> Path:
    """Return the isolated environment directory setup.py provisions into."""
    override = os.environ.get(VENV_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return REPO_ROOT / DEFAULT_VENV_DIRNAME


def repo_venv_python() -> Path:
    """Return the interpreter path inside the project virtual environment."""
    venv_dir = repo_venv_dir()
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def missing_required_modules() -> list[str]:
    """Return the modules main.py needs that this interpreter cannot import."""
    missing: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, AttributeError, ValueError):
            missing.append(name)
    return missing


def check_dependencies() -> bool:
    """Fail fast when the running interpreter is missing the app's dependencies.

    Called before any subprocess is spawned: if Streamlit cannot be imported there is
    no point starting llama-server, and doing so would leave an orphan process behind
    once the UI launch fails.

    Returns:
        True when every required module is importable, False otherwise.
    """
    missing = missing_required_modules()
    if not missing:
        return True

    venv_python = repo_venv_python()
    venv_hint = ""
    if venv_python.exists():
        venv_hint = (
            f"\n   A project environment already exists at {repo_venv_dir()}.\n"
            f"   Launch with that interpreter instead:\n"
            f"       {venv_python} start.py"
        )

    # Echo the user's own intent so the suggested command is a drop-in replacement.
    relaunch = f"{venv_python} start.py"
    if "--start-llama" in sys.argv:
        relaunch += " --start-llama"

    sys.stdout.flush()
    print(
        f"❌ Error: this Python interpreter is missing required modules: {', '.join(missing)}\n"
        f"   Interpreter: {sys.executable}\n"
        f"   The Streamlit UI cannot start, so llama-server was NOT launched.\n"
        f"\n"
        f"   Install the dependencies with:\n"
        f"       python3 setup.py\n"
        f"   That command creates {repo_venv_dir()} (or reuses it) and installs every\n"
        f"   dependency plus this package into it. Then launch with:\n"
        f"       {relaunch}"
        f"{venv_hint}\n"
        f"\n"
        f"   To install into this interpreter instead:\n"
        f"       {sys.executable} -m pip install -r requirements.txt",
        file=sys.stderr,
    )
    return False


def ensure_directories() -> None:
    """Ensure runtime persistence, tools, and cache directories exist."""
    dirs = [
        REPO_ROOT / "data",
        REPO_ROOT / ".cache",
        REPO_ROOT / "models",
        REPO_ROOT / "tools",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# Local artifacts: Qwen3.5-2B weights plus its F16 vision projector.
LOCAL_GGUF_FILENAME = "qwen3.5-2b-q4_k_m.gguf"
LOCAL_MMPROJ_FILENAME = "qwen3.5-2b-mmproj-f16.gguf"


def runtime_status_label() -> str:
    """Describe the installed native runtime relative to the expected build."""
    try:
        from core.runtime_info import runtime_status_line

        return runtime_status_line(REPO_ROOT)
    except Exception:
        return "llama-server not detected (run 'python setup.py --llama-server')"


def get_llama_server_binary() -> Path | None:
    """Locate llama-server executable on system PATH or local tools/ directory."""
    from core.runtime_info import find_llama_server_binary

    return find_llama_server_binary(REPO_ROOT)


def check_llama_server(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Check whether local llama-server is reachable and report status."""
    health_url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(health_url, headers={"User-Agent": "RAG-Launcher/1.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8", errors="ignore")
                data = json.loads(body) if body else {}
                status_str = data.get("status", "ok")
                print(f"  ✓ Local llama-server detected at {health_url} (status: {status_str})")
                return
    except urllib.error.HTTPError as he:
        if he.code == 503:
            print(f"  ⏳ Local llama-server at {health_url} is currently loading models...")
            return
        print(f"  ⚠️ Local llama-server returned HTTP {he.code}")
    except Exception:
        pass

    local_bin = get_llama_server_binary()
    bin_cmd = str(local_bin) if local_bin else "llama-server"

    print(f"  ℹ️ Local llama-server not detected at http://{host}:{port}")
    print("     The UI will launch in local offline mode (or user-consented cloud mode).")
    print(
        f"     To launch llama-server, run: {bin_cmd} -m models/{LOCAL_GGUF_FILENAME} "
        f"--mmproj models/{LOCAL_MMPROJ_FILENAME} -c 4096 -ngl 28 --port {port}"
    )
    print("     (Or start both together with: python start.py --start-llama)")


def start_llama_server_process(
    host: str = "127.0.0.1",
    port: int = 8080,
    ngl: int = 28,
    ctx: int = 4096,
) -> subprocess.Popen | None:
    """Spawn local llama-server as a background process and wait for initial probe."""
    bin_path = get_llama_server_binary()
    if not bin_path:
        print("❌ Error: llama-server executable not found on PATH or in tools/llama-server.", file=sys.stderr)
        print("   Run 'python setup.py --llama-server' to install it automatically.", file=sys.stderr)
        return None

    # Qwen3.5-2B weights and its matching Qwen3-VL merger projector.
    model_path = REPO_ROOT / "models" / LOCAL_GGUF_FILENAME
    mmproj_path = REPO_ROOT / "models" / LOCAL_MMPROJ_FILENAME

    if not model_path.exists():
        print(f"⚠️ Warning: Model weights not found at {model_path}.", file=sys.stderr)
        print("   Run 'python setup.py download_models' to download weights.", file=sys.stderr)
        return None
    if not mmproj_path.exists():
        print(f"⚠️ Warning: Vision projector not found at {mmproj_path}.", file=sys.stderr)
        print("   Run 'python setup.py download_models' to download the projector.", file=sys.stderr)
        return None

    # Verify what the artifacts actually are instead of trusting filenames.
    from core.model_identity import verify_local_model_pair

    identity_problems = verify_local_model_pair(model_path, mmproj_path)
    if identity_problems:
        print("❌ Model identity verification failed:", file=sys.stderr)
        for problem in identity_problems:
            print(f"   - {problem}", file=sys.stderr)
        print("   Refusing to launch llama-server with an incompatible model pair.", file=sys.stderr)
        return None

    cmd = [
        str(bin_path),
        "-m",
        str(model_path),
        "-c",
        str(ctx),
        "-ngl",
        str(ngl),
        "--port",
        str(port),
        "--host",
        host,
    ]
    if mmproj_path.exists():
        cmd.extend(["--mmproj", str(mmproj_path)])

    print(f"\n🚀 Launching local llama-server on http://{host}:{port} ...")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as err:
        print(f"❌ Failed to spawn llama-server: {err}", file=sys.stderr)
        return None

    # Poll /health for up to 10 seconds
    health_url = f"http://{host}:{port}/health"
    print("   Waiting for llama-server initialization...", end="", flush=True)
    for _ in range(20):
        time.sleep(0.5)
        try:
            req = urllib.request.Request(health_url, headers={"User-Agent": "RAG-Launcher/1.0"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status in (200, 503):
                    print(" ready!\n")
                    return proc
        except Exception:
            print(".", end="", flush=True)

    print(" continuing (server still initializing in background).\n")
    return proc


def launch_streamlit(port: int = 8501, host: str = "localhost", headless: bool = False) -> int:
    """Launch Streamlit frontend subprocess with forwarded arguments."""
    main_script = REPO_ROOT / "main.py"
    if not main_script.exists():
        print(f"❌ Error: main.py not found at {main_script}", file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(main_script),
        f"--server.port={port}",
        f"--server.address={host}",
        f"--server.headless={'true' if headless else 'false'}",
        "--browser.gatherUsageStats=false",
    ]

    print(f"\n🚀 Launching Streamlit web application on http://{host}:{port} ...")
    print("   Press Ctrl+C to stop the server.\n")

    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=os.environ.copy())
        return proc.returncode
    except KeyboardInterrupt:
        print("\n\n🛑 Application stopped by user.")
        return 0
    except Exception as err:
        print(f"\n❌ Error starting Streamlit process: {err}", file=sys.stderr)
        return 1


def main() -> int:
    """Entry point for project launcher."""
    parser = argparse.ArgumentParser(
        description="Launch Local-First Multimodal PDF Intelligence System",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument("--host", type=str, default="localhost", help="Streamlit bind address")
    parser.add_argument(
        "--allow-non-loopback",
        action="store_true",
        help=(
            "Allow a non-loopback --host bind. Only for trusted networks: the app has no "
            "authentication and exposes all indexed documents."
        ),
    )
    parser.add_argument("--headless", action="store_true", help="Run without opening browser automatically")
    parser.add_argument("--llama-host", type=str, default="127.0.0.1", help="llama-server host to probe")
    parser.add_argument("--llama-port", type=int, default=8080, help="llama-server port to probe")
    parser.add_argument(
        "--start-llama",
        action="store_true",
        help="Automatically launch local llama-server in background before launching UI",
    )
    parser.add_argument("--ngl", type=int, default=28, help="Number of GPU layers to offload to llama-server")
    parser.add_argument("--ctx", type=int, default=4096, help="Context window token size for llama-server")

    args = parser.parse_args()

    print_banner()

    if not check_python_version():
        return 1

    # Fail before any subprocess exists: a missing dependency would otherwise surface
    # only after llama-server had been started in the background.
    if not check_dependencies():
        return 3

    if not refuse_unsafe_bind(args.host, allow_non_loopback=args.allow_non_loopback):
        return 2

    ensure_directories()

    llama_proc = None
    if args.start_llama:
        llama_proc = start_llama_server_process(
            host=args.llama_host,
            port=args.llama_port,
            ngl=args.ngl,
            ctx=args.ctx,
        )
    else:
        check_llama_server(host=args.llama_host, port=args.llama_port)

    try:
        return launch_streamlit(port=args.port, host=args.host, headless=args.headless)
    finally:
        if llama_proc is not None:
            print("\n🛑 Stopping background llama-server...")
            try:
                llama_proc.terminate()
                llama_proc.wait(timeout=5)
            except Exception:
                llama_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
