# ------------------------------------------------------------------
# Baseline Performance Benchmark Script
# Measures extraction latency, chunk counts, CPU embedding time,
# in-memory linear vector search latency, and memory usage.
# Outputs metrics to .planning/research/BASELINE_BENCHMARK.json
# ------------------------------------------------------------------

import json
import os
import sys
import time
from pathlib import Path
import psutil

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pdf_reader import PdfReader
from vector_index import VectorIndex


def get_current_rss_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)


def run_benchmark():
    print("=" * 65)
    print(" BASELINE PERFORMANCE BENCHMARK (Phase 0: Baseline & Audit)")
    print("=" * 65)

    corpus_pdf = REPO_ROOT / "tests" / "data" / "corpus" / "clean_digital.pdf"
    if not corpus_pdf.exists():
        print(f"Error: Corpus PDF not found at {corpus_pdf}. Run generate_corpus.py first.")
        sys.exit(1)

    initial_rss = get_current_rss_mb()
    print(f"[Memory] Initial process RSS: {initial_rss:.2f} MB")

    # 1. Benchmark PDF Text Extraction with PdfReader (pypdf)
    print("\n[1/4] Benchmarking text extraction with pypdf...")
    t0 = time.perf_counter()
    reader = PdfReader(str(corpus_pdf))
    total_pages = len(reader.reader.pages)
    text = reader.extract_text()
    extraction_duration_s = time.perf_counter() - t0
    extraction_ms_per_page = (extraction_duration_s / total_pages) * 1000.0
    total_chars = len(text)

    print(f"  Pages: {total_pages}")
    print(f"  Total characters: {total_chars}")
    print(f"  Total extraction time: {extraction_duration_s:.4f} s")
    print(f"  Extraction latency per page: {extraction_ms_per_page:.2f} ms/page")

    # 2. Benchmark Paragraph / Chunk Generation
    print("\n[2/4] Benchmarking chunking (RecursiveCharacterTextSplitter)...")
    t0 = time.perf_counter()
    chunks = reader.get_paragraphs()
    chunking_duration_s = time.perf_counter() - t0
    print(f"  Total chunks generated: {len(chunks)}")
    print(f"  Chunking time: {chunking_duration_s * 1000:.2f} ms")

    # 3. Benchmark SentenceTransformer Embedding Generation (CPU)
    print("\n[3/4] Benchmarking embedding generation (SentenceTransformer on CPU)...")
    from sentence_transformers import SentenceTransformer

    before_model_rss = get_current_rss_mb()
    t0 = time.perf_counter()
    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    model_load_duration_s = time.perf_counter() - t0
    after_model_rss = get_current_rss_mb()
    model_rss_delta_mb = after_model_rss - before_model_rss
    print(f"  Model load time: {model_load_duration_s:.2f} s")
    print(f"  Memory increase from embedding model: {model_rss_delta_mb:.2f} MB (Current RSS: {after_model_rss:.2f} MB)")

    # Sample chunk texts for embedding latency
    chunk_texts = [c["content"] for c in chunks]
    batch_sizes = [min(10, len(chunk_texts)), min(20, len(chunk_texts)), len(chunk_texts)]
    batch_latencies = {}

    for b in batch_sizes:
        sample = chunk_texts[:b]
        t0 = time.perf_counter()
        _ = model.encode(sample, normalize_embeddings=True)
        dur_s = time.perf_counter() - t0
        batch_latencies[f"batch_{b}"] = {
            "count": b,
            "duration_seconds": round(dur_s, 4),
            "ms_per_chunk": round((dur_s / b) * 1000, 2),
        }
        print(f"  Batch {b} chunks: {dur_s:.3f} s ({(dur_s / b) * 1000:.2f} ms/chunk)")

    # 4. Benchmark In-Memory Linear Scan (VectorIndex)
    print("\n[4/4] Benchmarking VectorIndex linear scan latency (k=10)...")
    vector_dim = 384
    import numpy as np

    vector_counts = [100, 500, 1000]
    scan_latencies = {}

    for count in vector_counts:
        idx = VectorIndex(distance_metric="cosine")
        # Generate random normalized vectors
        np.random.seed(42)
        raw_vecs = np.random.randn(count, vector_dim).astype(np.float32)
        norms = np.linalg.norm(raw_vecs, axis=1, keepdims=True)
        normalized = (raw_vecs / norms).tolist()

        for i, vec in enumerate(normalized):
            idx.add_vector(vec, {"content": f"Document {i}", "id": i})

        # Run 5 searches and average
        query_vec = normalized[0]
        t0 = time.perf_counter()
        for _ in range(5):
            _ = idx.search(query_vec, k=10)
        dur_s = (time.perf_counter() - t0) / 5.0
        scan_latencies[f"vectors_{count}"] = {
            "count": count,
            "search_latency_ms": round(dur_s * 1000, 3),
        }
        print(f"  Scan over {count} vectors: {dur_s * 1000:.3f} ms")

    peak_rss = get_current_rss_mb()
    print(f"\n[Memory] Final process RSS: {peak_rss:.2f} MB (Total growth: {peak_rss - initial_rss:.2f} MB)")

    # Assemble JSON report
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": "00-baseline-and-audit",
        "hardware": {
            "cpu_cores": psutil.cpu_count(logical=True),
            "total_system_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
            "target_gpu": "NVIDIA RTX 3050 Laptop GPU (4 GB VRAM)",
        },
        "extraction_pypdf": {
            "pages": total_pages,
            "characters": total_chars,
            "total_duration_seconds": round(extraction_duration_s, 4),
            "latency_ms_per_page": round(extraction_ms_per_page, 2),
        },
        "chunking": {
            "total_chunks": len(chunks),
            "duration_ms": round(chunking_duration_s * 1000, 2),
        },
        "embeddings_cpu": {
            "model": "all-MiniLM-L6-v2",
            "model_load_seconds": round(model_load_duration_s, 2),
            "model_memory_mb": round(model_rss_delta_mb, 2),
            "batches": batch_latencies,
        },
        "vector_search_linear_scan": scan_latencies,
        "memory_profile": {
            "initial_rss_mb": round(initial_rss, 2),
            "peak_rss_mb": round(peak_rss, 2),
            "total_growth_mb": round(peak_rss - initial_rss, 2),
        },
    }

    output_path = REPO_ROOT / ".planning" / "research" / "BASELINE_BENCHMARK.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[Output] Baseline metrics successfully written to: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    run_benchmark()
