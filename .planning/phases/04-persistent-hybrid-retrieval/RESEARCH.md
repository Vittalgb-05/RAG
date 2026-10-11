# Phase 4: Persistent Hybrid Retrieval — Research

**Researched:** 2026-10-11  
**Domain:** Persistent embedded vector storage (LanceDB), CPU-pinned Sentence-Transformers (`all-MiniLM-L6-v2`), Full-Text Search (BM25/FTS), Reciprocal Rank Fusion (RRF), and unified retrieval contracts (`RetrievalResult`).  
**Confidence:** HIGH (APIs verified against LanceDB documentation, PyArrow schemas, SentenceTransformers CPU configuration, and established codebase patterns in `models.py` and `local_embedding.py`).

---

## 1. Current-State Analysis & Technical Debt

### 1.1 In-Memory Linear Vector Scan (`vector_index.py`, `local_embedding.py`)
- Currently, `VectorIndex` stores chunk dictionaries and vectors in plain in-memory Python lists (`self.vectors: list[list[float]]`, `self.documents: list[dict]`).
- It executes an $O(N)$ linear scan computing cosine distances with Python stdlib `math`.
- **Zero persistence across restarts:** When the Streamlit process or browser session restarts, the vector index is completely empty unless re-loaded through an SQLite dedup hit (`DocStore.get_chunks_for_doc` in `main.py:193-200`). Cold starts without file re-upload have no queryable vector index (`CONCERNS.md` "Vector index is in-memory only").
- Scaling limitation: Linear scan in pure Python begins to induce noticeable latency (>500ms) beyond 2,000 chunks (`PITFALLS.md`).

### 1.2 Keyword Blind Spots of Pure Dense Retrieval
- Dense embeddings (`all-MiniLM-L6-v2`) capture semantic meaning well (e.g. mapping "revenue" to "financial performance"), but frequently fail on exact keywords, technical codes, product numbers, acronyms, or specific table IDs (e.g. "RTX 3050", "Q4_K_M", "CR-01", "Table 4.2").
- Full-Text Search (BM25 / inverted index) directly solves this by scoring exact token occurrences, term frequencies, and document lengths.
- Combining both modalities via **Reciprocal Rank Fusion (RRF)** provides state-of-the-art hybrid recall without needing complex cross-encoder rerankers that would consume valuable GPU VRAM.

### 1.3 GPU Memory Protection on 4 GB VRAM Ceiling
- System runs on an NVIDIA RTX 3050 Laptop GPU with 4 GB VRAM.
- The local vision-language model (`llama-server` running Qwen3-VL 2B GGUF Q4_K_M + `mmproj-f16` + 4K context) requires ~3,260 MB of VRAM (`docs/LOCAL_INFERENCE.md`).
- If `SentenceTransformer` were to initialize on CUDA, PyTorch would allocate a CUDA context and reserved memory block (>500 MB), triggering CUDA out-of-memory (OOM) errors during VLM inference.
- **Requirement RETR-01** strictly mandates that `SentenceTransformer` runs on CPU (`device="cpu"`), preserving 100% of GPU VRAM for the VLM.

---

## 2. LanceDB Persistent Storage Architecture

### 2.1 Serverless Embedded Storage
- LanceDB (`lancedb>=0.17.0`) is a serverless, embedded vector and columnar database built on Apache Arrow and Lance file format.
- Similar to SQLite, it requires **no external database daemon, server process, or Docker container**.
- Connections are opened via local filesystem paths (`lancedb.connect("data/lancedb")`).
- Storage directory `data/lancedb` is naturally persisted on disk and ignored by git via `.gitignore:10` (`data/`).

### 2.2 Table Schema (`chunks`)
To represent canonical `Chunk` records and their 384-dimensional dense vectors, the LanceDB table schema includes:
```python
schema = {
    "chunk_id": str,          # Primary unique identifier, e.g. "sha12_p1_0000"
    "doc_id": str,            # Parent document ID, e.g. "doc_1234567812345678"
    "filename": str,          # Source filename
    "page": int,              # 1-indexed page number
    "content": str,           # Chunk text / markdown table content
    "vector": list[float],    # 384-dimensional float vector
    "extraction": str,        # "docling" | "ocr" | "pypdf"
    "char_start": int | None, # Character start offset on page
    "char_end": int | None,   # Character end offset on page
    "bbox_json": str | None,  # Serialized bounding box JSON
}
```

### 2.3 Operations
- **Table Initialization:** Open existing table (`db.open_table("chunks")`) or create if absent (`db.create_table("chunks", schema=..., mode="create")`).
- **Upsert / Overwrite:** Use `table.merge_insert("chunk_id")` or deduplicated insert to avoid duplicate chunks on re-indexing.
- **Deletion:** Delete by parent document: `table.delete(f"doc_id = '{doc_id}'")`.
- **Dense Vector Search:** `table.search(query_vector).limit(k).to_list()`.
- **Full-Text Search (FTS):** LanceDB supports full-text search indexing via Tantivy: `table.create_fts_index("content", replace=True)` and `table.search(query_text, query_type="fts").limit(k).to_list()`.

---

## 3. Reciprocal Rank Fusion (RRF) & Fallback Architecture

### 3.1 Reciprocal Rank Fusion Formula
Reciprocal Rank Fusion merges multiple ranked lists without needing score normalization (since cosine distance and BM25 scores have incompatible scales):
$$RRF\_score(d) = \sum_{m \in M} \frac{1}{k_{rrf} + rank_m(d)}$$
Where:
- $M = \{\text{dense}, \text{fts}\}$ (the retrieval modalities).
- $rank_m(d)$ is the 1-based rank of document $d$ in modality $m$.
- $k_{rrf}$ is the smoothing parameter (standard literature default is $60$).
- If document $d$ appears in only one list, it still receives a contribution from that modality.

### 3.2 Optional-Dependency Pattern & Deterministic Offline Fallback
In accordance with `CONVENTIONS.md:48-66`:
- `lancedb` must be imported conditionally (`try: import lancedb ... except ImportError: lancedb = None`).
- When `lancedb` is present and functional, `HybridRetriever` operates against on-disk LanceDB tables.
- When `lancedb` is not installed (e.g. in minimal test environments or prior to pip installation), `HybridRetriever` gracefully falls back to:
  1. Dense retrieval via `VectorIndex` (in-memory).
  2. Keyword retrieval via pure-Python BM25 scoring.
  3. Combination via explicit RRF fusion.
- This guarantees **100% offline testability** with zero failures even on systems lacking C-extensions or pre-compiled wheels.

---

## 4. Shared `RetrievalResult` Contract (RETR-04)

Currently, `AiModel` expects a plain string context from `LocalEmbedding.get_context()`, while `main.py` performs a separate query `local_embedding.search(prompt, k=10)` to display source filenames in the UI.

This creates two risks:
1. Divergence between what the LLM was grounded on and what the UI reports to the user.
2. Inability for the UI to display granular page numbers, bounding boxes, and exact snippet contents.

### 4.1 Canonical Schema (`models.py`)
```python
class EvidenceSnippet(BaseModel):
    """An individual retrieved evidence snippet with ranking and provenance."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    content: str
    doc_id: str
    filename: str
    page: int
    chunk_id: str
    score: float
    rank: int
    dense_rank: int | None = None
    fts_rank: int | None = None
    extraction: str = "docling"
    char_start: int | None = None
    char_end: int | None = None
    bbox: BBox | None = None

class RetrievalResult(BaseModel):
    """Immutable retrieval container shared identically across generation and UI citations."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    query: str
    snippets: list[EvidenceSnippet]
    total_candidates: int
    search_mode: Literal["hybrid", "dense", "fts", "fallback"]

    def formatted_context(self) -> str:
        """Render numbered evidence blocks ([E1], [E2], ...) for the LLM prompt."""
        blocks = []
        for s in self.snippets:
            header = f"[E{s.rank}] ({s.filename}, p. {s.page})"
            blocks.append(f"{header}\n{s.content}")
        return "\n\n---\n\n".join(blocks)
```

By passing a single immutable `RetrievalResult`:
- `prompt_budget.py` / `local_llm.py` consumes `retrieval_result.formatted_context()` to construct grounded prompts with explicit identifiers `[E1]`, `[E2]` (satisfying QA-02 in Phase 5).
- `main.py` directly renders `retrieval_result.snippets` as clickable source chips and evidence drawers (satisfying UI-03 in Phase 5).

---

## 5. Codebase Map Alignment

- **ARCHITECTURE.md**: Replaces the in-memory `VectorIndex` linear scan in the retrieval layer with persistent `HybridRetriever`. Maintains one-way dependency flow into canonical `models.py`.
- **CONCERNS.md**:
  - Direct mitigation of **"Vector index is in-memory only"**: LanceDB persists vectors and full-text inverted indices on disk in `data/lancedb/`.
  - Direct mitigation of **"Working-directory-relative artifact paths"**: LanceDB storage path is anchored to `Path(__file__).resolve().parent / "data" / "lancedb"`.
  - Direct mitigation of **"Chunk character offsets never populated"**: Preserves and passes `char_start`/`char_end` throughout `EvidenceSnippet`.
- **CONVENTIONS.md**:
  - Implements flat module structure at repository root (`hybrid_retriever.py`).
  - Follows optional-dependency pattern (`try: import lancedb ... except ImportError: lancedb = None`).
  - Strict Pydantic v2 idioms (`frozen=True`, `extra="forbid"`) for `EvidenceSnippet` and `RetrievalResult`.
  - Standard `logging` instead of `print`.
- **INTEGRATIONS.md**: LanceDB runs completely locally without external database server processes or network calls. SentenceTransformers pinned strictly to CPU.
- **STACK.md**: Adds `lancedb>=0.17.0` and `pyarrow>=14.0.0` to `requirements.txt`.
- **STRUCTURE.md**: Places `hybrid_retriever.py` in repo root and tests in `tests/test_hybrid_retriever.py`.
- **TESTING.md**: Verifies persistent store, RRF algorithm, and fallback mode with 100% offline unit tests.
