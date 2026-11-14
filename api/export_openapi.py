"""Export OpenAPI schema definition to openapi.json with drift checking."""

from __future__ import annotations
import argparse
import contextlib
import json
import sys
from pathlib import Path

# Ensure UTF-8 stdout/stderr across Windows consoles (cp1252/cp437)
if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.main import app


def export_openapi(check: bool = False) -> int:
    """Generate OpenAPI specification and write to file or check for drift."""
    spec = app.openapi()
    content = json.dumps(spec, indent=2, ensure_ascii=False) + "\n"
    out_file = Path("openapi.json")

    if check:
        if not out_file.exists():
            sys.stderr.write("[ERROR] openapi.json does not exist. Run 'python -m api.export_openapi' to generate.\n")
            return 1
        existing = out_file.read_text(encoding="utf-8")
        if existing.strip() != content.strip():
            sys.stderr.write("[ERROR] openapi.json is out of date with current FastAPI routers. Run 'python -m api.export_openapi'.\n")
            return 1
        sys.stdout.write("[OK] openapi.json is up to date.\n")
        sys.stdout.flush()
        return 0

    out_file.write_text(content, encoding="utf-8")
    sys.stdout.write(f"[OK] openapi.json exported ({len(content)} bytes).\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export or verify OpenAPI specification")
    parser.add_argument("--check", action="store_true", help="Verify openapi.json is up to date without overwriting")
    args = parser.parse_args()
    sys.exit(export_openapi(check=args.check))
