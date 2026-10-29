# Local Inference Runbook: Qwen3.5-2B on RTX 3050 Laptop GPU (4 GB VRAM)

This runbook guides running local multimodal inference for the PDF Intelligence System on an **NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM)** using `llama-server` (llama.cpp **v0.8.0**, build `b11960`) with zero cloud network egress.

---

## 1. Hardware & VRAM Allocation Profile

The system is calibrated to execute safely within a **4,096 MB VRAM ceiling** on Windows 11 without triggering shared GPU system memory paging:

Measured on the target machine (`nvidia-smi`, Windows 11, driver 592.82) with the server idle after model load:

| Component | VRAM Allocation | Notes |
| :--- | :--- | :--- |
| **Qwen3.5-2B Q4_K_M weights** | ~1,310 MB | 25-block hybrid DeltaNet/attention backbone, `-ngl 28` |
| **Vision projector F16** | ~668 MB | `qwen3vl_merger` projector, offloaded to GPU by default |
| **KV cache (`-c 4096`)** | ~250 MB | bounded context; the checkpoint itself supports 262,144 tokens |
| **CUDA runtime + desktop compositor** | ~430 MB | driver context, cuBLAS buffers, Windows DWM |
| **Total measured** | **2,658 MiB of 4,096 MiB** | **Headroom ~1.4 GB.** The previous Qwen2-VL-2B pair measured 2,987 MiB on the same machine, so this migration reduced VRAM pressure by ~330 MiB. |

If VRAM is contended (other GPU applications open), add `--no-mmproj-offload` to keep the projector on CPU; image analysis slows down but loading still succeeds.

---

## 2. Prerequisites

1. **NVIDIA Driver**: 550.x or higher with CUDA 12.x support.
2. **llama.cpp v0.8.0 (build `b11960`)**: Windows x64 CUDA 12.4 build `llama-b11960-bin-win-cuda-12.4-x64.zip` plus the matching `cudart-llama-bin-win-cuda-12.4-x64.zip` runtime.
   - Download from the [b11960 release](https://github.com/ggml-org/llama.cpp/releases/tag/b11960) (the `v0.8.0` release itself attaches only `nightly-tag.txt`, which names `b11960`).
   - `python setup.py --llama-server` performs the download, SHA-256 verification, extraction, and a `--version` smoke check.
   - Verified digests: `8d9d819261de10cc2f03921b8b79c779c5c458e21edb60c170ee30a7d462d684` (binaries) and `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6` (cudart).
   - Extract `llama-server.exe` and dependent `.dll` files into `tools/llama-server` or your PATH. The v0.8.0 loader resolves `ggml-cuda.dll`/`cudart64_12.dll` from the same directory.

---

## 3. Model Download

Create a `models/` directory in the repository root and download the quantized GGUF weights:

```powershell
mkdir -p models
```

1. **Text & Vision Model (`Q4_K_M`)**:
   - Filename: `qwen3.5-2b-q4_k_m.gguf` (1,312,165,056 bytes; GGUF `general.architecture=qwen35`, `general.name="Qwen3.5 2B"`)
2. **Vision Projector**:
   - Filename: `qwen3.5-2b-mmproj-f16.gguf` (668,227,136 bytes; `clip.projector_type=qwen3vl_merger`, 768 px images, patch 16, 24 vision blocks)

Both come from `SoAIHQ/Qwen3.5-2B-GGUF` at revision `377fa65bb36aa83414de1ab3b40f6f15b0324cdc`, licensed Apache-2.0 (inherited from `Qwen/Qwen3.5-2B`). Their SHA-256 digests match the publisher's `SHA256SUMS`: `a8b50de0…1523b` (weights) and `044a0ea1…d36` (projector). `llama.cpp` v0.8.0 recognises both the `qwen35` architecture and the `qwen3vl_merger` projector.

Verify the pair before launching (the launcher also refuses mismatched artifacts):

```powershell
python -c "from core.model_identity import verify_local_model_pair; print(verify_local_model_pair('models/qwen3.5-2b-q4_k_m.gguf', 'models/qwen3.5-2b-mmproj-f16.gguf') or 'identity OK')"
```

---

## 4. Starting `llama-server`

Run the following command in PowerShell:

```powershell
llama-server `
  -m models/qwen3.5-2b-q4_k_m.gguf `
  --mmproj models/qwen3.5-2b-mmproj-f16.gguf `
  -c 4096 `
  -ngl 28 `
  -b 512 `
  -ub 512 `
  --reasoning-budget 0 `
  --port 8080 `
  --host 127.0.0.1
```

### Parameter Breakdown
- `-m`: Path to the quantized GGUF model weights (`Q4_K_M`).
- `--mmproj`: Path to the multimodal projector for visual document reading (`mmproj-f16`).
- `-c 4096`: Bounds the context window to 4,096 tokens, preventing VRAM overflow.
- `-ngl 28`: Offloads every model layer (the checkpoint has 25) to the NVIDIA GPU.
- `--reasoning-budget 0`: Stops the default Qwen3.5 thinking pass so grounded answers are not crowded out of the bounded context. (`--reasoning off` is equivalent; the app sends `reasoning_effort: "none"` per request instead of relying on the server default.)
- `-b 512`: Sets logical batch size to 512 tokens to prevent transient VRAM allocation spikes during prompt ingestion.
- `-ub 512`: Sets physical micro-batch size to 512 tokens for bounded CUDA workspace memory.
- `--port 8080`: Local REST API endpoint.
- `--host 127.0.0.1`: Binds strictly to localhost (no external network exposure).

### Scaling to 8K Context (Optional with KV Quantization)
To expand context window from 4,096 to 8,192 tokens while remaining within the 4 GB VRAM ceiling, enable Q8_0 KV cache quantization and Flash Attention:
```powershell
llama-server `
  -m models/qwen3.5-2b-q4_k_m.gguf `
  --mmproj models/qwen3.5-2b-mmproj-f16.gguf `
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
*Note: `-ctk q8_0 -ctv q8_0` halves KV-cache bytes relative to FP16, which is what made the 8K profile fit on the previous model. Qwen3.5-2B uses a hybrid DeltaNet/attention backbone, so its KV footprint is smaller than a same-size dense model at the same context; re-measure with `nvidia-smi` before relying on 8K in production.*

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

The sidebar status reflects the active provider's reported capabilities: it shows `Local · qwen3.5-2b` when the local server answers `/health` with 200, `Provider loading` on HTTP 503, and `Cloud · <model>` only after consented cloud mode is enabled. The Settings and Diagnostics workspaces additionally report the runtime version detected from the installed `llama-server` binary (for example `llama.cpp 0.8.0-dev (build 11960) - matches expected v0.8.0 (b11960)`).

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
