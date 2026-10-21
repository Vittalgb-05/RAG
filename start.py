"""One-command application launcher for Local-First Multimodal PDF Intelligence System.

Usage:
    python start.py
    python start.py --port 8501 --host localhost
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Ensure UTF-8 stdout/stderr across Windows consoles (cp1252/cp437)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

REPO_ROOT = Path(__file__).resolve().parent


def print_banner() -> None:
    """Print ASCII startup banner."""
    print("=" * 68)
    print("  📄 Local-First Multimodal PDF Intelligence System")
    print("  Hybrid Search • RapidOCR • Docling • Qwen2-VL 2B • Verifiable Citations")
    print("=" * 68)


def check_python_version() -> bool:
    """Verify minimum Python 3.11 requirement."""
    if sys.version_info < (3, 11):
        print(f"❌ Error: Python 3.11+ required. Detected: {sys.version.split()[0]}", file=sys.stderr)
        return False
    return True


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


def get_llama_server_binary() -> Path | None:
    """Locate llama-server executable on system PATH or local tools/ directory."""
    on_path = shutil.which("llama-server")
    if on_path:
        return Path(on_path)
    local_bin = (
        REPO_ROOT / "tools" / "llama-server" / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
    )
    if local_bin.exists():
        return local_bin
    return None


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
        f"     To launch llama-server, run: {bin_cmd} -m models/qwen3-vl-2b-instruct-q4_k_m.gguf "
        f"--mmproj models/mmproj-f16.gguf -c 4096 -ngl 28 --port {port}"
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

    # Legacy artifact filename; GGUF metadata reports Qwen2-VL-2B-Instruct.
    model_path = REPO_ROOT / "models" / "qwen3-vl-2b-instruct-q4_k_m.gguf"
    mmproj_path = REPO_ROOT / "models" / "mmproj-f16.gguf"

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
