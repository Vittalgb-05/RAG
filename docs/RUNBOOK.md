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

### Step 2: Install Dependencies

Use the tested production lockfile:
```bash
pip install --upgrade pip
pip install -r requirements-lock.txt
```

> **Windows Symlink Tip**: If Hugging Face Hub warns about symlinks during embedding model downloads, either enable Developer Mode in Windows Settings (`Settings > System > For developers > Developer Mode`) or set the environment variable:
> ```powershell
> $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
> ```

---

## 3. Local Model Acquisition (llama.cpp)

### Step 1: Download `llama-server`

Download the pre-compiled `llama.cpp` release with CUDA support from the [official llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases):
- **Windows**: `llama-bXXXX-bin-win-cuda-cu12.4-x64.zip` (unzip and ensure `llama-server.exe` is in your PATH or in the repository root).
- **Linux**: Compile with `make GGML_CUDA=1` or download the pre-built Linux CUDA package.

### Step 2: Download Model Weights

Create a `models/` directory in the repository root:
```bash
mkdir models
```

Download the 4-bit quantized Qwen3-VL 2B model and multimodal projection weights:
```bash
# 1. Main model GGUF (~1.4 GB)
curl -L -o models/qwen3-vl-2b-instruct-q4_k_m.gguf https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct-GGUF/resolve/main/qwen2-vl-2b-instruct-q4_k_m.gguf

# 2. Multimodal projection adapter GGUF (~600 MB)
curl -L -o models/mmproj-f16.gguf https://huggingface.co/Qwen/Qwen2-VL-2B-Instruct-GGUF/resolve/main/mmproj-qwen2-vl-2b-instruct-f16.gguf
```

---

## 4. Starting the Local Inference Server

Launch `llama-server` with parameters specifically tuned for 4 GB VRAM systems:

### Windows PowerShell:
```powershell
.\llama-server.exe `
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf `
  --mmproj models/mmproj-f16.gguf `
  -c 4096 `
  -ngl 28 `
  --host 127.0.0.1 `
  --port 8080
```

### Linux / Bash:
```bash
./llama-server \
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf \
  --mmproj models/mmproj-f16.gguf \
  -c 4096 \
  -ngl 28 \
  --host 127.0.0.1 \
  --port 8080
```

### Flag Breakdown:
- `-m models/qwen3-vl-2b-instruct-q4_k_m.gguf`: Base language model with 4-bit quantization.
- `--mmproj models/mmproj-f16.gguf`: Vision adapter required for image/figure understanding.
- `-c 4096`: Context window capped at 4,096 tokens to bound KV-cache allocation.
- `-ngl 28`: Offloads all 28 transformer layers to GPU VRAM (~2.4 GB total allocation).
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
   - RapidOCR fallback on scanned pages (< 30 characters detected).
   - Visual figure cropping and Qwen3-VL 2B captioning.
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
