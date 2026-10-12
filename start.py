"""One-command application launcher for Local-First Multimodal PDF Intelligence System.

Usage:
    python start.py
    python start.py --port 8501 --host localhost
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent


def print_banner() -> None:
    """Print ASCII startup banner."""
    print("=" * 68)
    print("  📄 Local-First Multimodal PDF Intelligence System")
    print("  Hybrid Search • RapidOCR • Docling • Qwen3-VL 2B • Verifiable Citations")
    print("=" * 68)


def check_python_version() -> bool:
    """Verify minimum Python 3.11 requirement."""
    if sys.version_info < (3, 11):
        print(f"❌ Error: Python 3.11+ required. Detected: {sys.version.split()[0]}", file=sys.stderr)
        return False
    return True


def ensure_directories() -> None:
    """Ensure runtime persistence and cache directories exist."""
    dirs = [
        REPO_ROOT / "data",
        REPO_ROOT / ".cache",
        REPO_ROOT / "models",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


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

    print(f"  ℹ️ Local llama-server not detected at http://{host}:{port}")
    print("     The UI will launch in local offline mode (or user-consented cloud mode).")
    print("     To launch llama-server, run: llama-server -m models/... --mmproj models/... --port 8080")


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
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
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

    args = parser.parse_args()

    print_banner()

    if not check_python_version():
        return 1

    ensure_directories()
    check_llama_server(host=args.llama_host, port=args.llama_port)

    return launch_streamlit(port=args.port, host=args.host, headless=args.headless)


if __name__ == "__main__":
    sys.exit(main())
