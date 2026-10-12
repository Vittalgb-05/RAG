# Phase 6: Performance Optimization & Resource Profiling — Research & Technical Specification

**Author:** Antigravity Engineering  
**Date:** 2026-10-12  
**Phase:** 6  
**Requirements:** `QUAL-01`  
**Hardware & Environment Constraints:** NVIDIA GeForce RTX 3050 Laptop GPU (4 GB VRAM ceiling, 3.8 GB target), Windows 11 host (DWM overhead ~487 MB observed), local CPU embeddings, local LanceDB / SQLite persistence, 100% offline & CI testability.

---

## 1. Executive Summary & Hardware Context

Phase 6 hardens and tunes the entire system to guarantee rock-solid stability within the **4,096 MB VRAM hardware ceiling** of the user's **NVIDIA GeForce RTX 3050 Laptop GPU**:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                   RTX 3050 Laptop GPU (4,096 MB VRAM Total)                  │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ Component                     │ VRAM Consumption Profile                    │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Windows OS & DWM Overhead     │ ~487 MB (Observed live via nvidia-smi)      │
│ Qwen3-VL 2B Base (Q4_K_M)     │ ~1,450 MB (Offloaded via -ngl 28)           │
│ Multimodal Projector (f16)    │ ~450 MB (Vision adapter mmproj-f16.gguf)    │
│ KV Cache (4K Context, FP16)   │ ~510 MB (Bounded by -c 4096)                │
│ CUDA Runtime & Scratch Buffers│ ~350 MB (cuBLAS / compute workspace)        │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ Total Peak Allocated          │ ~3,247 MB                                   │
│ Safety Headroom Remaining     │ ~849 MB (Strictly below 3,800 MB target)    │
└───────────────────────────────┴─────────────────────────────────────────────┘
```

### Core Deliverables for Phase 6:
1. **Single-Active-LLM Concurrency Lock (`QUAL-01`):** Enforce an atomic thread gate ensuring that only a single GPU inference request executes at any given instant across all Streamlit sessions or background worker threads, preventing out-of-memory (OOM) crashes from overlapping calls.
2. **Resource Telemetry & Monitoring Module (`resource_telemetry.py`):** Provide live tracking of process RAM (RSS via `psutil`), GPU VRAM allocation & headroom (via headless-safe `nvidia-smi` queries), and stage-by-stage latency timings.
3. **Multi-Tier Cache Invalidation & Resolution of Dual-Index Debt:** Rationalize caching across four tiers (Streamlit session state, `.cache/` disk extraction, `doc_store.py` SQLite, `hybrid_retriever.py` LanceDB) and eliminate redundant in-memory vector index duplication noted in `CONCERNS.md`.
4. **VRAM Profiling & Benchmarking Harness (`scripts/profile_resources.py`):** Deliver an automated script that benchmarks cold vs. warm document processing, context scaling, and cache hits, outputting empirical telemetry to `.planning/research/RESOURCE_PROFILE.json`.
5. **Streamlit UI Resource Monitor:** Embed lightweight hardware health indicators into the sidebar displaying real-time VRAM allocation, RAM usage, and cache hit metrics.

---

## 2. Requirement Analysis & Technical Blueprint

### 2.1 Hardware Calibration for RTX 3050 Laptop GPU (`QUAL-01`)

#### 2.1.1 VRAM Allocation Math
- **Base Model (`Q4_K_M`):** 28 transformer layers offloaded to GPU with `-ngl 28`. Quantized weights occupy ~1,450 MB.
- **Vision Projector (`mmproj-f16`):** Dedicated cross-attention weights mapping visual patches to text embedding space occupy ~450 MB.
- **KV Cache Calculations:**
  - Formula for GQA/MQA KV cache size:
    $$\text{KV VRAM (bytes)} = 2 \times n_{\text{layers}} \times n_{\text{kv\_heads}} \times d_{\text{head}} \times c_{\text{ctx}} \times \text{bytes\_per\_element}$$
  - At FP16 (2 bytes/element) with 4,096 context tokens: $\approx 510\text{ MB}$.
  - At 8,192 context tokens without quantization: $\approx 1,020\text{ MB}$.
  - With Q8_0 KV cache quantization (`-ctk q8_0 -ctv q8_0`): $\approx 255\text{ MB}$ at 4K tokens, $\approx 510\text{ MB}$ at 8K tokens.
- **Operating System Baseline:**
  Windows 11 Desktop Window Manager (DWM) and display driver buffers consume between 450 MB and 550 MB on the primary display. Live query via `nvidia-smi` confirms 487 MB in use at idle.
- **Recommended `llama-server` Launch Parameters:**
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
  *(Note: `-b 512` and `-ub 512` bound the logical batch size during prompt ingestion, avoiding transient VRAM spikes during long prompt ingest).*

#### 2.1.2 Single-Active-LLM Concurrency Lock (`QUAL-01`)
Because Streamlit executes script reruns in worker threads and users can trigger multiple interactions (e.g. streaming a chat response while summarization is triggered), a concurrency guard is essential:
- Implement `InferenceGate` in `local_llm.py` (or `resource_telemetry.py`):
  ```python
  class InferenceGate:
      """Process-level reentrant lock ensuring single active GPU inference."""
      _lock = threading.Lock()

      @classmethod
      def acquire(cls, timeout: float = 60.0) -> bool:
          return cls._lock.acquire(timeout=timeout)

      @classmethod
      def release(cls) -> None:
          cls._lock.release()
  ```
- Wrap all calls in `AiModel.stream_text`, `AiModel.generate_text`, and `Summarizer.summarize_document` to prevent concurrent GPU execution.
- If lock cannot be acquired within timeout, return a user-friendly diagnostic message rather than crashing.

---

## 3. Multi-Tier Caching Architecture & Memory Limits

The system operates four distinct caching tiers. Phase 6 formalizes their lifecycle, invalidation semantics, and memory boundaries:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Tier 1: In-Memory Session State                        │
│   Streamlit `st.session_state` (chat history, summary widgets, metadata)    │
│   - Bound chat history to max 50 turns to prevent browser memory growth     │
│   - Clear All handler purges `summary_*` and resets retrieval state         │
├─────────────────────────────────────────────────────────────────────────────┤
│                      Tier 2: Disk Extraction Cache                          │
│   `.cache/<sha256>/<CONFIG_VERSION>/{pages,chunks,manifest}.json`            │
│   - Fast-path for repeated ingestion of identical PDFs                      │
│   - Invalidation triggered when `CONFIG_VERSION` changes                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                      Tier 3: Persistent SQLite DocStore                     │
│   `data/documents.db` (documents, pages, chunks, summaries v3)              │
│   - Persistent metadata store with WAL mode & busy_timeout=5000             │
│   - `get_summary(sha256, profile, model_version)` with version invalidation │
│   - Delivers < 50ms response on repeated summary requests                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                      Tier 4: LanceDB Vector & Keyword Index                 │
│   `data/lancedb/` (dense vectors + inverted index chunks)                   │
│   - Deduplication by chunk_id on upload                                     │
│   - Purge & document delete synchronization to reclaim disk space           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Addressing Dual-Index Memory Debt (from `CONCERNS.md`)
In Phase 4, uploads populated both `LocalEmbedding` (in-memory `VectorIndex`) and `HybridRetriever` (on-disk LanceDB). In Phase 6:
- We streamline the primary retrieval path: `HybridRetriever` is the sole index in session state.
- `LocalEmbedding` serves strictly as the CPU embedding generator (providing `_embed_one` and batch vectors) without maintaining a redundant duplicate vector store in RAM.
- This saves ~150–300 MB of process RAM on large corpora and eliminates state divergence.

---

## 4. Resource Telemetry & Performance Monitoring (`resource_telemetry.py`)

A dedicated, lightweight telemetry module (`resource_telemetry.py`) provides non-intrusive monitoring:

### 4.1 GPU Metrics Engine
```python
def get_gpu_memory_info() -> dict[str, float] | None:
    """Query NVIDIA GPU memory via nvidia-smi with graceful fallback for CI/headless."""
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=2.0)
        line = result.stdout.strip().split("\n")[0]
        total_mb, used_mb, free_mb = [float(x.strip()) for x in line.split(",")]
        return {
            "total_mb": total_mb,
            "used_mb": used_mb,
            "free_mb": free_mb,
            "utilization_pct": round((used_mb / total_mb) * 100, 1),
        }
    except Exception:
        return None
```

### 4.2 Process RAM Engine
```python
def get_process_memory_info() -> dict[str, float]:
    """Query current process RSS and virtual memory via psutil."""
    try:
        import psutil
        proc = psutil.Process()
        mem = proc.memory_info()
        return {
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
        }
    except Exception:
        return {"rss_mb": 0.0, "vms_mb": 0.0}
```

### 4.3 Stage Latency Profiler
A context manager `track_latency(stage_name: str)` records execution durations and logs telemetry metrics for:
- PDF text & table extraction
- Chunk embedding generation (SentenceTransformers CPU)
- Hybrid search (LanceDB dense + BM25 FTS)
- First-token latency & generation throughput
- Summarization map & reduce stages

---

## 5. Implementation Roadmap (Phases 06-01 & 06-02)

### Plan 06-01: Resource Profiling, Concurrency Gate & VRAM Benchmarks
1. Create `resource_telemetry.py` with GPU (`nvidia-smi`), RAM (`psutil`), and operation latency tracking.
2. Implement thread-safe `InferenceGate` concurrency lock in `local_llm.py` ensuring max 1 active GPU inference call at a time (`QUAL-01`).
3. Author `scripts/profile_resources.py` to automate end-to-end benchmarking under cold and warm states, measuring VRAM, RSS, and latency, and writing `.planning/research/RESOURCE_PROFILE.json`.
4. Update `docs/LOCAL_INFERENCE.md` with calibrated tuning instructions for 4 GB VRAM systems.
5. Create unit tests `tests/test_resource_telemetry.py` verifying telemetry extraction and headless degradation.

### Plan 06-02: Multi-Tier Cache Invalidation, Memory Bounds & UI Telemetry
1. Eliminate redundant in-memory `VectorIndex` duplicate storage from `main.py` ingestion loop, using `HybridRetriever` as the single index of truth.
2. Implement cache management helpers in `doc_store.py` and `main.py`:
   - Enforce max 50 chat turns in `st.session_state.chat_history` to prevent browser tab RAM bloat.
   - Comprehensive reset button that cleans session keys and optionally flushes disk caches.
3. Integrate real-time Resource Monitoring Widget into Streamlit sidebar:
   - GPU VRAM meter (Used / Total MB) with safe status indicators (green `< 3.5 GB`, amber `3.5–3.8 GB`, red `> 3.8 GB`).
   - Process RAM footprint (RSS MB).
   - Cache hit status badge.
4. Create test suite `tests/test_cache_invalidation.py` verifying multi-tier cache hits, eviction, and memory bounding.
