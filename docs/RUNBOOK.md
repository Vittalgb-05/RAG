# 📘 Operational Runbook: Local-First Multimodal RAG Assistant

> **Target Systems**: Windows 11 (tested on NVIDIA GeForce RTX 3050 Laptop GPU, 4 GB VRAM) & Linux x86_64.  
> **Last Verified**: Phase 8 Release Hardening.

---

## 1. System Requirements & Hardware Budget

| Component | Minimum Requirement | Recommended Specification |
|---|---|---|
| **OS** | Windows 11 64-bit / Ubuntu 22.04 LTS | Windows 11 / Ubuntu 24.04 LTS |
| **GPU** | NVIDIA GPU with 4 GB VRAM (RTX 3050) | NVIDIA GPU with 6+ GB VRAM |
| **CUDA** | CUDA 11.8 or CUDA 12.x | CUDA 12.4+ |
| **System RAM** | 16 GB DDR4/DDR5 | 16 GB or 32 GB DDR5 |
| **Storage** | 10 GB available SSD space | Fast NVMe SSD |
| **Python** | Python 3.11 or 3.12 | Python 3.11.x |

---

## 2. Installation & Setup

### Step 1: Clone Repository & Create Virtual Environment

```bash
git clone https://github.com/Vittalgb-05/RAG.git
cd RAG

python -m venv .venv
```

Activate the environment:
- **Windows PowerShell**:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  .\.venv\Scripts\Activate.ps1
  ```
- **Linux / macOS**:
  ```bash
  source .venv/bin/activate
  ```

### Step 2: Automated Full Setup (Recommended)

Run the all-in-one setup tool to install dependencies, verify directories, download required GGUF models, and pre-cache local embedding and OCR models:
```bash
python setup.py
```

If the system interpreter refuses `pip install` (PEP 668 `EXTERNALLY-MANAGED`, the default on Ubuntu 24.04 and other distros), setup creates an isolated environment and installs everything into it instead of failing. It then prints the exact interpreter to launch with, for example:
```bash
.venv/bin/python start.py --start-llama      # Linux / macOS
.venv\Scripts\python.exe start.py --start-llama   # Windows
```
Setup exits non-zero when dependencies still cannot be installed, so a green run always means the printed interpreter can start the app. Override the environment location with `python setup.py --venv-path /path/to/env` or `RAG_VENV_PATH=/path/to/env`. An existing usable environment is reused, never rebuilt.

Or run dedicated sub-commands as needed:
```bash
# Explicit full setup using requirements-lock.txt
python setup.py setup --lockfile

# Install only Python dependencies
python setup.py --deps-only

# Download only local models (GGUF weights + embedding/OCR cache)
python setup.py download_models
# Or via CLI flag:
python setup.py --models-only

# Standard editable package install
pip install -e .
```

> **Windows Symlink Tip**: If Hugging Face Hub warns about symlinks during embedding model downloads, either enable Developer Mode in Windows Settings (`Settings > System > For developers > Developer Mode`) or set the environment variable:
> ```powershell
> $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
> ```

---

## 3. Local Model Acquisition (llama.cpp)

### Step 1: Automated Download of `llama-server` via `setup.py`

`setup.py` automatically detects your GPU (CUDA on NVIDIA GPUs vs CPU) and installs `llama-server` into `tools/llama-server/`:
```bash
python setup.py --llama-server
```
*(Or run `python setup.py` for the complete initial setup: dependencies, models, and llama-server in one pass).*

`--llama-server` is deliberately llama-only: it never installs Python packages. After configuring the binary it runs a dependency pre-flight and prints the launch command to use — or, if the app dependencies are still missing, the exact install command (`python setup.py`) and the interpreter to launch with. `start.py` performs the same check before it spawns anything, so a missing `streamlit` fails immediately with the interpreter path and remediation instead of after llama-server has started.

The expected runtime is **llama.cpp v0.8.0, published as nightly build `b11960`** (the `v0.8.0` release asset `nightly-tag.txt` names that build; binaries are attached to the `b11960` tag). Verify the installed executable reports itself:

```bash
./tools/llama-server/llama-server.exe --version
# version: 0.8.0-dev (build 11960, commit 8642541b2)
```

Alternatively, you can manually download `llama.cpp` releases from the [official llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases/tag/b11960):
- **Windows**: `llama-b11960-bin-win-cuda-12.4-x64.zip` + `cudart-llama-bin-win-cuda-12.4-x64.zip` (extract into `tools/llama-server` or system PATH). Verified SHA-256: `8d9d819261de10cc2f03921b8b79c779c5c458e21edb60c170ee30a7d462d684` and `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`.
- **Linux**: `llama-b11960-bin-ubuntu-cuda-12.8-x64.tar.gz` (`64d57beb9abb637c177c6afb313760a0c0782224cac71e74869eed5b8f9a1ea4`) or compile with `make GGML_CUDA=1`.
- **Rollback**: the previous verified runtime (`0.7.0-dev`, build `11718`) is kept in `tools/llama-server-b11718-rollback/`; see the rollback section at the end of this runbook.

### Step 2: Download Model Weights & Pre-Cache Offline Models

#### Option A: Automated via `setup.py` (Recommended)
```bash
python setup.py download_models
```
This automatically downloads:
1. `models/qwen3.5-2b-q4_k_m.gguf` (Qwen3.5-2B Q4_K_M weights, GGUF architecture `qwen35`)
2. `models/qwen3.5-2b-mmproj-f16.gguf` (F16 vision projector, `clip.projector_type=qwen3vl_merger`)
3. Pre-caches SentenceTransformers `all-MiniLM-L6-v2` embedding weights in local HuggingFace cache.
4. Pre-caches RapidOCR ONNX model weights in local cache for offline execution.

#### Option B: Manual Download (Alternative)
Create a `models/` directory in the repository root:
```bash
mkdir models
```

Download the 4-bit quantized Qwen3.5-2B weights and their F16 multimodal projector from `SoAIHQ/Qwen3.5-2B-GGUF` (Apache-2.0), pinned to revision `377fa65bb36aa83414de1ab3b40f6f15b0324cdc`:
```bash
# 1. Main model GGUF (1,312,165,056 bytes)
curl -L -o models/qwen3.5-2b-q4_k_m.gguf https://huggingface.co/SoAIHQ/Qwen3.5-2B-GGUF/resolve/377fa65bb36aa83414de1ab3b40f6f15b0324cdc/Qwen3.5-2B-Q4_K_M.gguf

# 2. Multimodal projection adapter GGUF (668,227,136 bytes)
curl -L -o models/qwen3.5-2b-mmproj-f16.gguf https://huggingface.co/SoAIHQ/Qwen3.5-2B-GGUF/resolve/377fa65bb36aa83414de1ab3b40f6f15b0324cdc/mmproj-Qwen3.5-2B-f16.gguf
```

Verify both the pinned SHA-256 digests and the GGUF identity before launching (the digests match the publisher's `SHA256SUMS` file):

```bash
sha256sum models/qwen3.5-2b-q4_k_m.gguf models/qwen3.5-2b-mmproj-f16.gguf
# expected:
# a8b50de00b780c0f3c16f07cb041a1ecd678b6e22fd8cde91e57fe4b5031523b  models/qwen3.5-2b-q4_k_m.gguf
# 044a0ea136cca70711ae16e23b24d754b44eab6f2462d187aee4d7c7a9503d36  models/qwen3.5-2b-mmproj-f16.gguf
```

On Windows PowerShell, use `Get-FileHash -Algorithm SHA256 <path>`.

`python setup.py download_models` verifies these digests automatically (set `RAG_REQUIRE_CHECKSUMS=1` to fail closed on any unpinned artifact), and `start.py` refuses to launch a mismatched pair:

```bash
python -c "from core.model_identity import verify_local_model_pair; print(verify_local_model_pair('models/qwen3.5-2b-q4_k_m.gguf', 'models/qwen3.5-2b-mmproj-f16.gguf') or 'identity OK')"
```

---

## 4. Starting the Local Inference Server

Launch `llama-server` with parameters specifically tuned for 4 GB VRAM systems:

### Windows PowerShell:
```powershell
# Option 1: Automatic combined launch (starts llama-server and Streamlit UI together)
python start.py --start-llama

# Option 2: Run llama-server manually in a separate window
.\tools\llama-server\llama-server.exe `
  -m models/qwen3.5-2b-q4_k_m.gguf `
  --mmproj models/qwen3.5-2b-mmproj-f16.gguf `
  -c 4096 `
  -ngl 28 `
  --host 127.0.0.1 `
  --port 8080
```

### Linux / Bash:
```bash
./llama-server \
  -m models/qwen3.5-2b-q4_k_m.gguf \
  --mmproj models/qwen3.5-2b-mmproj-f16.gguf \
  -c 4096 \
  -ngl 28 \
  --host 127.0.0.1 \
  --port 8080
```

### Flag Breakdown:
- `-m models/qwen3.5-2b-q4_k_m.gguf`: Base language model with 4-bit (Q4_K_M) quantization; 25 blocks, 2,048-dim embeddings.
- `--mmproj models/qwen3.5-2b-mmproj-f16.gguf`: Vision adapter required for image/figure understanding.
- `-c 4096`: Context window capped at 4,096 tokens to bound KV-cache allocation (the checkpoint supports 262,144 tokens; the ceiling is a VRAM decision, not a model limit).
- `-ngl 28`: Offloads every model layer (the model has 25) plus the F16 projector to GPU; measured 2,658 MiB of 4,096 MiB. Use `--no-mmproj-offload` if VRAM is contended.
- `--host 127.0.0.1`: Binds strictly to local loopback interface for SSRF security.
- `--port 8080`: Default local inference port monitored by the application.

### Verify Server Health:
Open another terminal and run:
```bash
curl http://127.0.0.1:8080/health
# Expected output: {"status":"ok"}
```

---

## 5. Starting the Application

### Option A: Launcher Script (Recommended)
Run `start.py` to perform automatic pre-flight checks, verify directories, probe `llama-server`, and launch the web interface:
```bash
python start.py
```

### Option B: Direct Streamlit Run
```bash
streamlit run main.py
```

Streamlit will launch and display:
```
Local URL: http://localhost:8501
Network URL: http://...
```
Navigate to `http://localhost:8501` in your browser.

---

## 6. Operational Procedures

### Document Ingestion Runbook
1. Drag and drop any PDF document into the sidebar uploader.
2. Ingestion validation enforces:
   - Maximum file size: **50 MB**
   - Maximum page count: **500 pages**
   - File signature check: Must start with `%PDF` magic bytes.
3. Ingestion executes through:
   - SHA-256 deduplication (skips re-indexing if content is identical).
   - Layout-aware Docling table and structure parsing.
   - RapidOCR fallback on scanned pages (< 50 characters detected).
   - Visual figure cropping and Qwen3.5-2B captioning.
   - LanceDB dense vector indexing + SQLite FTS5 lexical indexing.

### Live Telemetry Monitoring
- Inspect the sidebar **System Telemetry** expander:
  - **GPU VRAM**: Displays current VRAM used, free, and utilization percentage (cached with a 5.0-second TTL to avoid process-spawn latency).
  - **Process RAM**: Tracks current application resident set size (RSS).
  - **Pipeline Latencies**: Displays execution times for extraction, retrieval, and generation.

### Optional Cloud Mode Activation
1. In the sidebar, toggle **Enable Cloud Inference**.
2. Review the **Data Privacy Consent Dialog** modal.
3. Click **I Consent & Enable Cloud**.
4. Select provider (`Groq`, `OpenAI`, or `Anthropic`) and enter an in-memory session API key (or configure `GROQ_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` in `.env`).

---

## 7. Troubleshooting & Recovery Runbook

### Issue 1: `llama-server unreachable` in Sidebar
- **Cause**: Server process is not running or is bound to a different port.
- **Remedy**:
  1. Check terminal running `llama-server`.
  2. Verify endpoint connectivity: `curl http://127.0.0.1:8080/health`.
  3. Ensure no firewall software is blocking loopback socket communication on port 8080.

### Issue 2: CUDA Out of Memory (OOM) / System Thrashing
- **Cause**: Other applications (e.g. web browser with hardware acceleration, game, video editor) are consuming VRAM.
- **Remedy**:
  1. Check VRAM usage via `nvidia-smi`.
  2. Reduce GPU layer offloading: run `llama-server` with `-ngl 24` or `-ngl 20` instead of `-ngl 28`.
  3. Reduce context window: run with `-c 2048`.

### Issue 3: Missing Optional Extraction Packages
- **Cause**: `docling`, `rapidocr-onnxruntime`, or `pymupdf` are optional dependencies in constrained environments.
- **Behavior**: The application automatically degrades gracefully:
  - Ingestion falls back to standard `pypdf` text extraction.
  - Image OCR falls back to standard text extraction without failing.
  - LanceDB falls back to in-memory cosine index if native binaries cannot load.

### Issue 4: Corrupt or Stale Extraction Cache
- **Remedy**:
  Use the "Purge All Data" button in the sidebar, or manually clear cache files:
  ```bash
  # Windows PowerShell
  Remove-Item -Recurse -Force .cache/
  # Linux
  rm -rf .cache/
  ```

---

## 8. Deployment Architecture: Workstation Scoping & Privacy

### Single-User Workstation Assumption
- **Design Intent**: This application is architected and validated as a personal desktop workstation tool where Streamlit and `llama-server` execute concurrently on the same local system (`127.0.0.1`).
- **Session-Scoped Routing**: Individual browser sessions maintain their own isolated `AiModel` instances and ephemeral cloud-consent posture. One session toggling Cloud Mode does not alter the local-only routing of another session.
- **Hosted Cloud Caveat**: Deploying the Streamlit frontend to external services (e.g., Streamlit Community Cloud) cannot access `127.0.0.1:8080` on your laptop. Hosted deployments require remote endpoint configuration with dedicated API keys and TLS encryption.

---

## 9. Rollback to the Previous Runtime and Model

The `v0.8.0`/Qwen3.5-2B migration keeps the previous verified artifacts on disk, so a rollback is a rename plus a restart. Nothing below deletes user documents, indexes, or caches.

**Runtime (llama.cpp).** The previous executable and its DLL set remain in `tools/llama-server-b11718-rollback/`:

```bash
# Stop the current server first, then:
mv tools/llama-server tools/llama-server-v0.8.0
mv tools/llama-server-b11718-rollback tools/llama-server
./tools/llama-server/llama-server.exe --version   # version: 0.7.0-dev (build 11718, commit 547208dca)
```

**Model (Qwen2-VL-2B).** The previous weights are still at `models/qwen3-vl-2b-instruct-q4_k_m.gguf` and `models/mmproj-f16.gguf` (legacy filenames; GGUF metadata is authoritative and verified by `core.model_identity`). Start the server with those paths instead:

```bash
./tools/llama-server/llama-server.exe \
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf \
  --mmproj models/mmproj-f16.gguf \
  -c 4096 -ngl 28 --port 8080
```

`core.model_identity.SUPPORTED_MODEL_PAIRS` accepts the `qwen2vl` + `qwen2vl_merger` pair, so the launcher's identity check passes without a code change. Two notes:

- Running the old model while the code default points at Qwen3.5 only changes what `start.py --start-llama` launches; a manually started server is unaffected, but the provider's `model_name` label stays `qwen3.5-2b` and evidence rows will be tagged `vlm:qwen3.5-2b`. Relabel after a rollback if provenance matters.
- The verified `b11718` runtime has no `--reasoning-effort` flag, but it accepts the request unchanged and ignores the unknown `reasoning_effort` / `chat_template_kwargs` fields (verified by running the old model through the current provider payload).
