"""Setup and packaging configuration for Local-First Multimodal PDF Intelligence System.

Provides automated dependency installation, local model downloading, and setuptools packaging.

Usage:
    python setup.py                 # Full setup: install dependencies, create directories, download models
    python setup.py setup           # Explicit full setup
    python setup.py download_models # Download only models (GGUF weights + embedding/OCR cache)
    python setup.py --models-only   # Download only models via CLI flag
    python setup.py --deps-only     # Install only dependencies via pip
    pip install -e .                # Standard editable package install
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from setuptools import Command, find_packages, setup

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

REPO_ROOT = Path(__file__).resolve().parent

# Read the long description from README.md
readme_path = REPO_ROOT / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

# Read core dependencies from requirements.txt
req_path = REPO_ROOT / "requirements.txt"
requirements = []
if req_path.exists():
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            requirements.append(line)


MODEL_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "qwen3-vl-2b-instruct-q4_k_m.gguf",
        "description": "Qwen2-VL 2B Instruct GGUF (4-bit quantized base language/vision model)",
        "min_size_bytes": 800_000_000,
        "urls": [
            "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
            "https://huggingface.co/lmstudio-community/Qwen2-VL-2B-Instruct-GGUF/resolve/main/Qwen2-VL-2B-Instruct-Q4_K_M.gguf",
        ],
    },
    {
        "name": "mmproj-f16.gguf",
        "description": "Qwen2-VL 2B Multimodal Projector Adapter GGUF (FP16 vision encoder)",
        "min_size_bytes": 500_000_000,
        "urls": [
            "https://huggingface.co/bartowski/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
            "https://huggingface.co/lmstudio-community/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-Qwen2-VL-2B-Instruct-f16.gguf",
        ],
    },
]


def ensure_project_directories() -> None:
    """Ensure runtime persistence and cache directories exist."""
    dirs = [
        REPO_ROOT / "models",
        REPO_ROOT / "data",
        REPO_ROOT / ".cache",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("✓ Project directories initialized (models/, data/, .cache/)")


def format_bytes(size: int | float) -> str:
    """Format bytes into human-readable size string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def download_file_with_progress(
    urls: list[str],
    dest_path: Path,
    min_size_bytes: int = 1_000_000,
    force: bool = False,
) -> bool:
    """Download a remote file with streaming progress bar and fallback mirrors.

    Args:
        urls: List of mirror URLs to attempt in order.
        dest_path: Destination file path on local filesystem.
        min_size_bytes: Minimum expected file size for integrity verification.
        force: If True, re-download even if a valid file exists.

    Returns:
        True if successfully downloaded or already present, False otherwise.
    """
    if not force and dest_path.exists():
        current_size = dest_path.stat().st_size
        if current_size >= min_size_bytes:
            print(f"  ✓ {dest_path.name} already exists ({format_bytes(current_size)}), skipping.")
            return True
        else:
            print(f"  ⚠️ Existing {dest_path.name} is undersized ({format_bytes(current_size)}). Re-downloading...")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".tmp")

    headers = {"User-Agent": "RAG-Model-Downloader/1.0"}

    for idx, url in enumerate(urls, start=1):
        print(f"  ⬇️ Downloading {dest_path.name} (Mirror {idx}/{len(urls)})...")
        print(f"     URL: {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                start_time = time.monotonic()
                last_print_time = start_time
                chunk_size = 256 * 1024  # 256 KB buffer

                with open(temp_path, "wb") as f_out:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()

                        if now - last_print_time >= 0.5 or (total_size and downloaded >= total_size):
                            last_print_time = now
                            elapsed = max(0.1, now - start_time)
                            speed = downloaded / elapsed
                            if total_size > 0:
                                pct = (downloaded / total_size) * 100.0
                                bar_len = 24
                                filled = int(bar_len * downloaded / total_size)
                                bar = "=" * filled + "-" * (bar_len - filled)
                                sys.stdout.write(
                                    f"\r     [{bar}] {pct:5.1f}% | {format_bytes(downloaded)} / {format_bytes(total_size)} | {format_bytes(speed)}/s"
                                )
                            else:
                                sys.stdout.write(
                                    f"\r     Downloaded {format_bytes(downloaded)} | {format_bytes(speed)}/s"
                                )
                            sys.stdout.flush()

                sys.stdout.write("\n")

            if temp_path.stat().st_size < min_size_bytes:
                print(f"  ⚠️ Warning: Downloaded file size ({temp_path.stat().st_size} bytes) below threshold.")
                temp_path.unlink(missing_ok=True)
                continue

            # Atomically replace destination
            if dest_path.exists():
                dest_path.unlink()
            shutil.move(str(temp_path), str(dest_path))
            print(f"  ✓ Successfully verified and saved {dest_path.name} ({format_bytes(dest_path.stat().st_size)})")
            return True

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"\n  ❌ Mirror {idx} failed: {err}")
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            continue

    print(f"  ❌ Error: All mirrors failed for {dest_path.name}")
    return False


def precache_embedding_model(model_name: str = "all-MiniLM-L6-v2") -> bool:
    """Download and pre-cache SentenceTransformer model into local cache."""
    print(f"\n🧠 Pre-caching local embedding model: {model_name}...")
    try:
        os.environ.setdefault("USE_TF", "0")
        os.environ.setdefault("USE_TORCH", "1")
        from sentence_transformers import SentenceTransformer

        # Warm up process cache and verify model weights exist
        _ = SentenceTransformer(model_name, device="cpu")
        print(f"  ✓ Embedding model '{model_name}' successfully cached in local HuggingFace cache.")
        return True
    except ImportError:
        print("  ℹ️ sentence-transformers not yet installed in current environment; skipping pre-cache.")
        return False
    except Exception as err:
        print(f"  ⚠️ Warning: Failed to pre-cache embedding model '{model_name}': {err}")
        return False


def precache_ocr_model() -> bool:
    """Download and pre-cache RapidOCR ONNX model weights."""
    print("\n🔍 Pre-caching RapidOCR ONNX models...")
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR

        _ = RapidOCR()
        print("  ✓ RapidOCR ONNX weights verified and ready for offline inference.")
        return True
    except ImportError:
        print("  ℹ️ rapidocr not installed in current environment; skipping pre-cache.")
        return False
    except Exception as err:
        print(f"  ⚠️ Warning: Could not initialize RapidOCR: {err}")
        return False


def download_all_models(
    models_dir: Path | None = None,
    force: bool = False,
    skip_vlm: bool = False,
) -> bool:
    """Download all required models: GGUF weights, embeddings, and OCR.

    Args:
        models_dir: Destination directory for GGUF models (default: models/).
        force: If True, overwrite existing files.
        skip_vlm: If True, skip large GGUF downloads and only pre-cache embeddings/OCR.

    Returns:
        True if all requested downloads succeeded.
    """
    target_dir = models_dir or (REPO_ROOT / "models")
    target_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 68)
    print("  📦 MODEL ACQUISITION & OFFLINE CACHE WARM-UP")
    print("=" * 68)

    all_ok = True
    if not skip_vlm:
        for model in MODEL_REGISTRY:
            dest = target_dir / model["name"]
            print(f"\n• {model['description']}")
            ok = download_file_with_progress(
                urls=model["urls"],
                dest_path=dest,
                min_size_bytes=model["min_size_bytes"],
                force=force,
            )
            if not ok:
                all_ok = False
    else:
        print("  ℹ️ Skipping large VLM GGUF model download as requested (--skip-vlm).")

    # Pre-cache embedding and OCR models
    precache_embedding_model()
    precache_ocr_model()

    print("\n" + "=" * 68)
    if all_ok:
        print("  ✓ All required models are ready for local offline inference!")
    else:
        print("  ⚠️ Some models could not be downloaded automatically.")
        print("     Please refer to docs/RUNBOOK.md for manual download links.")
    print("=" * 68)
    return all_ok


def install_dependencies(
    use_lockfile: bool = False,
    upgrade: bool = False,
) -> bool:
    """Install project dependencies using pip.

    Args:
        use_lockfile: If True, install from requirements-lock.txt instead of requirements.txt.
        upgrade: If True, pass --upgrade to pip.

    Returns:
        True if pip install exited with code 0.
    """
    req_file = REPO_ROOT / ("requirements-lock.txt" if use_lockfile else "requirements.txt")
    if not req_file.exists():
        print(f"❌ Error: {req_file} not found.", file=sys.stderr)
        return False

    print("=" * 68)
    print(f"  📦 INSTALLING DEPENDENCIES ({req_file.name})")
    print("=" * 68)

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    if upgrade:
        cmd.append("--upgrade")

    try:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
        if proc.returncode == 0:
            print(f"\n✓ Successfully installed dependencies from {req_file.name}")
            return True
        else:
            print(f"\n❌ pip install exited with status {proc.returncode}", file=sys.stderr)
            return False
    except Exception as err:
        print(f"\n❌ Error running pip: {err}", file=sys.stderr)
        return False


def run_full_setup(
    skip_vlm: bool = False,
    force_models: bool = False,
    use_lockfile: bool = False,
) -> int:
    """Execute complete initial setup: directories, dependencies, and model downloads."""
    print("=" * 68)
    print("  🚀 Local-First Multimodal PDF Intelligence System — Setup")
    print("=" * 68)

    ensure_project_directories()

    # Step 1: Install dependencies
    deps_ok = install_dependencies(use_lockfile=use_lockfile)
    if not deps_ok:
        print("⚠️ Warning: Dependency installation reported issues. Continuing with model download...")

    # Step 2: Download models
    download_all_models(
        models_dir=REPO_ROOT / "models",
        force=force_models,
        skip_vlm=skip_vlm,
    )

    # Step 3: Install current package in editable mode
    print("\n📦 Registering local package...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", "."],
            cwd=str(REPO_ROOT),
            check=False,
        )
    except Exception:
        pass

    print("\n" + "=" * 68)
    print("  🎉 Setup Complete!")
    print("  To launch the application, run:")
    print("      python start.py")
    print("=" * 68 + "\n")
    return 0


class DownloadModelsCommand(Command):
    """Custom setuptools command to download local models."""

    description = "Download all local GGUF models and pre-cache embedding and OCR weights"
    user_options = [
        ("models-dir=", None, "Target directory for GGUF model files (default: models/)"),
        ("force", "f", "Force re-download even if files already exist"),
        ("skip-vlm", None, "Skip downloading large VLM GGUF models (cache embeddings/OCR only)"),
    ]

    def initialize_options(self) -> None:
        self.models_dir = "models"
        self.force = False
        self.skip_vlm = False

    def finalize_options(self) -> None:
        self.models_dir = str((REPO_ROOT / self.models_dir).resolve())

    def run(self) -> None:
        download_all_models(
            models_dir=Path(self.models_dir),
            force=bool(self.force),
            skip_vlm=bool(self.skip_vlm),
        )


def main_cli() -> int:
    """CLI entry point for rag-setup command."""
    return run_full_setup()


def download_models_cli() -> int:
    """CLI entry point for rag-download-models command."""
    parser = argparse.ArgumentParser(description="Download models for Local-First Multimodal RAG Assistant")
    parser.add_argument("--models-dir", type=str, default="models", help="Destination folder for GGUF models")
    parser.add_argument("--force", action="store_true", help="Force re-download even if files already exist")
    parser.add_argument("--skip-vlm", action="store_true", help="Skip downloading large VLM GGUF models")
    args = parser.parse_args()

    ok = download_all_models(
        models_dir=REPO_ROOT / args.models_dir,
        force=args.force,
        skip_vlm=args.skip_vlm,
    )
    return 0 if ok else 1


# Standard setuptools setup call
setup_kwargs: dict[str, Any] = dict(
    name="rag-assistant",
    version="1.0.0",
    description="Local-First Multimodal PDF Intelligence System with Hybrid Retrieval and VLM",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="RAG Team",
    python_requires=">=3.11",
    packages=find_packages(),
    py_modules=[
        "citation_validator",
        "doc_store",
        "docling_reader",
        "groq_provider",
        "hybrid_retriever",
        "litellm_provider",
        "llama_cpp_provider",
        "local_embedding",
        "local_llm",
        "main",
        "model_provider",
        "models",
        "ocr_fallback",
        "pdf_reader",
        "prompt_budget",
        "resource_telemetry",
        "setup",
        "start",
        "summarizer",
        "upload_validation",
        "vector_index",
        "visual_analyzer",
    ],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "rag-assistant=start:main",
            "rag-setup=setup:main_cli",
            "rag-download-models=setup:download_models_cli",
        ],
    },
    cmdclass={
        "download_models": DownloadModelsCommand,
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)


if __name__ == "__main__":
    raw_args = sys.argv[1:]

    custom_flags = {"--deps-only", "--models-only", "--skip-vlm", "--lockfile", "--force"}
    is_custom_invocation = bool(
        not raw_args
        or raw_args[0] in ("setup", "--setup", "download_models", "download-models")
        or any(arg in custom_flags for arg in raw_args)
    )

    if is_custom_invocation:
        # Filter out sub-command keyword if present for argparse
        filtered_args = list(raw_args)
        is_download_cmd = False
        if filtered_args and filtered_args[0] in ("setup", "--setup"):
            filtered_args.pop(0)
        elif filtered_args and filtered_args[0] in ("download_models", "download-models"):
            filtered_args.pop(0)
            is_download_cmd = True

        parser = argparse.ArgumentParser(
            description="Set up dependencies and download models for RAG Assistant",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        )
        parser.add_argument("--deps-only", action="store_true", help="Only install Python dependencies")
        parser.add_argument("--models-only", action="store_true", help="Only download models and caches")
        parser.add_argument("--models-dir", type=str, default="models", help="Destination folder for GGUF models")
        parser.add_argument("--skip-vlm", action="store_true", help="Skip downloading large VLM GGUF models")
        parser.add_argument("--force", action="store_true", help="Force re-download existing model files")
        parser.add_argument("--lockfile", action="store_true", help="Use requirements-lock.txt for install")

        parsed, _ = parser.parse_known_args(filtered_args)

        if parsed.deps_only:
            ensure_project_directories()
            sys.exit(0 if install_dependencies(use_lockfile=parsed.lockfile) else 1)
        elif parsed.models_only or is_download_cmd:
            ensure_project_directories()
            target_dir = REPO_ROOT / parsed.models_dir
            sys.exit(
                0 if download_all_models(models_dir=target_dir, force=parsed.force, skip_vlm=parsed.skip_vlm) else 1
            )
        else:
            sys.exit(
                run_full_setup(
                    skip_vlm=parsed.skip_vlm,
                    force_models=parsed.force,
                    use_lockfile=parsed.lockfile,
                )
            )

    # Otherwise delegate to setuptools (e.g. `python setup.py bdist_wheel`, `python setup.py sdist`)
    setup(**setup_kwargs)
