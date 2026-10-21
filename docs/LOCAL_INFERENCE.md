# Local Inference Runbook: Qwen2-VL 2B on RTX 3050 Laptop GPU (4 GB VRAM)

This runbook guides running local multimodal inference for the PDF Intelligence System on an **NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM)** using `llama-server` (llama.cpp) with zero cloud network egress.

---

## 1. Hardware & VRAM Allocation Profile

The system is calibrated to execute safely within a **4,096 MB VRAM ceiling** on Windows 11 without triggering shared GPU system memory paging:

| Component | VRAM Allocation | Notes |
| :--- | :--- | :--- |
| **Model Weights (`Q4_K_M`)** | ~1,450 MB | Qwen2-VL 2B quantized base weights offloaded to GPU |
| **Vision Projector (`mmproj-f16`)** | ~450 MB | Multimodal projector for diagram and image analysis |
| **KV Cache (`-c 4096`)** | ~510 MB | 4K token bounded context window |
| **CUDA Runtime Overhead** | ~350 MB | Driver context and cuBLAS buffers |
| **Windows Desktop Window Manager** | ~500 MB | OS display compositor reserved VRAM |
| **Total Peak VRAM Footprint** | **~3,260 MB** | **Headroom: ~830 MB (Well under 4 GB ceiling)** |

---

## 2. Prerequisites

1. **NVIDIA Driver**: 550.x or higher with CUDA 12.x support.
2. **llama.cpp**: Release with CUDA support (e.g., `llama-bXXXX-bin-win-cuda-cu12.4-x64.zip`).
   - Download from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases).
   - Extract `llama-server.exe` and dependent `.dll` files into your PATH or a tools directory.

---

## 3. Model Download

Create a `models/` directory in the repository root and download the quantized GGUF weights:

```powershell
mkdir -p models
```

1. **Text & Vision Model (`Q4_K_M`)**:
   - Filename: `qwen3-vl-2b-instruct-q4_k_m.gguf` (~1.45 GB)
2. **Vision Projector**:
   - Filename: `mmproj-f16.gguf` (~450 MB)

*(Weights can be downloaded directly from Hugging Face repositories hosting quantized Qwen-VL GGUF models).*

---

## 4. Starting `llama-server`

Run the following command in PowerShell:

```powershell
llama-server `
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf `
  --mmproj models/mmproj-f16.gguf `
  -c 4096 `
  -ngl 28 `
  -b 512 `
  -ub 512 `
  --port 8080 `
  --host 127.0.0.1
```

### Parameter Breakdown
- `-m`: Path to the quantized GGUF model weights (`Q4_K_M`).
- `--mmproj`: Path to the multimodal projector for visual document reading (`mmproj-f16`).
- `-c 4096`: Bounds the context window to 4,096 tokens, preventing VRAM overflow.
- `-ngl 28`: Offloads all 28 transformer layers to the NVIDIA GPU.
- `-b 512`: Sets logical batch size to 512 tokens to prevent transient VRAM allocation spikes during prompt ingestion.
- `-ub 512`: Sets physical micro-batch size to 512 tokens for bounded CUDA workspace memory.
- `--port 8080`: Local REST API endpoint.
- `--host 127.0.0.1`: Binds strictly to localhost (no external network exposure).

### Scaling to 8K Context (Optional with KV Quantization)
To expand context window from 4,096 to 8,192 tokens while remaining within the 4 GB VRAM ceiling, enable Q8_0 KV cache quantization and Flash Attention:
```powershell
llama-server `
  -m models/qwen3-vl-2b-instruct-q4_k_m.gguf `
  --mmproj models/mmproj-f16.gguf `
  -c 8192 `
  -ctk q8_0 `
  -ctv q8_0 `
  -fa `
  -ngl 28 `
  -b 512 `
  -ub 512 `
  --port 8080 `
  --host 127.0.0.1
```
*Note: With `-ctk q8_0 -ctv q8_0`, the 8K KV cache occupies ~510 MB VRAM, identical to a 4K FP16 KV cache.*

---

## 5. Verifying Server Health

Verify the server status via `curl` or PowerShell `Invoke-RestMethod`:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8080/health"
```

Expected response when ready:
```json
{"status": "ok"}
```

If the model is still loading into VRAM, the server returns HTTP 503 (`{"status": "loading model"}`), which the RAG system displays with a loading status badge in the sidebar.

---

## 6. Hybrid & Cloud Fallback Mode

If `llama-server` is not running or if GPU memory is occupied by other tasks, the application automatically falls back to Groq Cloud inference if a `GROQ_API_KEY` is present in your `.env` or Streamlit secrets:

```env
GROQ_API_KEY=gsk_your_groq_api_key_here
```

When Groq is used, the sidebar badge indicates `🔵 Inference: Groq Cloud (openai/gpt-oss-20b)`. When local `llama-server` is active, it indicates `🟢 Inference: Local (qwen3-vl-2b)`.

---

## 7. Troubleshooting

### 1. Shared GPU Memory Spilling (High Latency)
- **Symptom**: Token generation drops from ~35 tokens/s to <3 tokens/s.
- **Cause**: Total VRAM usage exceeded 4 GB, causing Windows NVIDIA driver to page memory to host RAM.
- **Fix**: Lower offloaded layers slightly: `-ngl 24` or reduce context window: `-c 3072`.

### 2. Connection Refused at `http://127.0.0.1:8080`
- **Symptom**: Sidebar shows `⚠️ Inference: Offline (setup required)`.
- **Fix**: Launch `llama-server` using the command in Section 4. The UI will automatically detect the server once started without requiring an application restart.

---

## 8. Concurrency Safety & Resource Profiling (`QUAL-01`)

### Single-Active-LLM Concurrency Lock (`InferenceGate`)
To strictly guarantee that multiple browser sessions or concurrent background operations do not collide and cause CUDA out-of-memory errors on 4 GB GPUs, the application enforces an atomic reentrant lock (`InferenceGate` in `local_llm.py`).
- All token streaming (`AiModel.ask_a_question_from_pdf_stream`), direct generations (`AiModel.generate_text`), and multi-page summarization batches (`Summarizer.summarize_document`) execute exclusively.
- If a secondary request arrives while GPU inference is active, it waits safely up to timeout (60s) or informs the user rather than crashing the GPU driver.

### Automated Resource Profiling Suite
You can benchmark cold vs. warm ingestion, retrieval, summarization caching, process RAM, and GPU VRAM footprint using the automated benchmark script:
```powershell
python scripts/profile_resources.py
```
This script benchmarks the system against synthetic multi-page documents and writes empirical metrics to `.planning/research/RESOURCE_PROFILE.json`.
