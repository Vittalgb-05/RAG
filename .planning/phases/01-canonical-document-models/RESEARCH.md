# Phase 1: Canonical Document Models & Storage Foundation — Research

**Researched:** 2026-10-10
**Domain:** Typed document modeling (Pydantic) + SQLite metadata store + Streamlit upload validation
**Confidence:** HIGH (all current-state claims verified by direct source reads this session)

## Summary

Phase 1 replaces three fragile foundations in the prototype: (1) untyped chunk dicts
(`{content, filename, page, chunk_id}`), (2) session-only metadata (`st.session_state`
dicts/sets lost on restart), and (3) filename-keyed dedup with no byte validation
(any extension-renamed file passes `type=["pdf"]`). The fix is three new flat modules
following the repo's one-class-per-file convention — `models.py` (Pydantic v2 schemas),
`doc_store.py` (sqlite3-backed ACID store), `upload_validation.py` (magic-byte/size/page-cap
checks + streaming SHA-256) — plus a thin Streamlit progress layer in `main.py` reusing the
existing `st.status` idiom.

**Primary recommendation:** Use Pydantic v2 (already installed: 2.11.9) + Python `sqlite3`
stdlib (SQLite 3.49.1) with short-lived per-operation connections; do NOT introduce
SQLAlchemy/aiosqlite as new required deps. Key the disk cache by `{sha256}/{config_version}/`.

## 1. Current-State Analysis (all VERIFIED by direct reads)

### 1.1 Upload / index loop — `main.py:121-161`

- Upload gate is extension-only: `st.file_uploader("Upload PDFs", type=["pdf"], ...)`
  (`main.py:113-119`). No magic-byte, size, or page-count check exists.
- Dedup key is `uploaded_file.name` (`main.py:126,146`): renaming the same bytes
  re-indexes; two different files with the same name collide (second silently skipped).
- Whole file is buffered twice per upload: `uploaded_file.getvalue()` at `main.py:131`
  (BytesIO) — plus `save_uploaded_pdf()` (`main.py:69-80`) buffers again via
  `NamedTemporaryFile(delete=False)` and is currently dead code on the main path.
- Per-file isolation exists: `try/except Exception → st.error → continue`
  (`main.py:133-138`) — INGEST-05's UI half already works; it needs extending to
  page-level isolation inside extraction.
- Session state keys (`main.py:44-51`): `indexed_files: set`, `document_metadata: dict`
  (`{upload_time, pages, chunks}` at `main.py:147-151`), `local_embedding`, `chat_history`.
  All volatile — restart/re-deploy wipes the index (matches ARCHITECTURE.md "In-memory only").
- Progress idiom is `st.status("Processing documents…")` + `st.write(...)` per stage +
  `.update(label=..., state="complete")` (`main.py:95-97,123-161`). UI-01 must extend this,
  not replace it.

### 1.2 Chunk dict shape — `pdf_reader.py:48-56` [VERIFIED]

```python
{"content": p.strip(), "filename": self.filename, "page": page_num, "chunk_id": f"{self.filename}_p{page_num}_{j}"}
```

- `VectorIndex` requires the `content` key (`vector_index.py:55-56,83-84`); `main.py:149`
  reads `paragraphs[-1]["page"]`; `main.py:218` reads `doc["filename"]`.
  New Pydantic `Chunk` must serialize back to exactly these keys (via `model_dump()` /
  `model_dump_json()`) so `LocalEmbedding.build_index`, `VectorIndex`, and `main.py`
  keep working unchanged.
- Chunking constants are inline literals: `chunk_size=1000, chunk_overlap=200`
  (`pdf_reader.py:31-33`). These become part of the cache config-version string (STORE-03).
- `PdfReader.__init__(file_or_path, filename=None)` accepts path str / bytes / file object
  (`pdf_reader.py:10-21`); extraction is whole-document (`extract_text`) with no per-page
  try/except — one corrupt page aborts the file. INGEST-05 work goes here.

### 1.3 Index API — `local_embedding.py` / `vector_index.py` [VERIFIED]

- `LocalEmbedding.build_index(chunks: list)` accepts `list[str]` or `list[dict]`
  (`local_embedding.py:42-59`); `search(question, k=3)`, `get_context(question, k=3)`.
- `VectorIndex` is pure stdlib (`math`, `typing` only), linear-scan O(n) k-NN, dimension
  lock-in on first insert, `search()` returns `[]` on empty store (`vector_index.py:110-111`).
- Phase 1 does NOT touch retrieval internals — it only changes what dicts get fed in
  (now Pydantic-validated) and where metadata persists (SQLite alongside, not inside,
  the vector store). Phase 4 (LanceDB) replaces the vector layer.

### 1.4 Test patterns to extend — `tests/` [VERIFIED]

- `conftest.py`: `fake_env_groq_key`, `mock_groq_client`, `mock_sentence_transformer`
  (deterministic 384-dim vectors), `sample_pdf_path`. New tests reuse
  `mock_sentence_transformer` + corpus PDFs; no new heavy fixtures needed.
- Style: dashed banner header, one behavior per test, `pytest.raises(match=...)` for guards
  (`test_vector_index.py:47-74`), corpus-backed integration (`test_pdf_reader.py:15-26`).
  New files: `tests/test_models.py`, `tests/test_doc_store.py`, `tests/test_upload_validation.py`.
- Corpus available: `clean_digital.pdf` (20 pages), `multi_column.pdf`, `dense_table.pdf`,
  `chart_diagram.pdf`, `scanned_sample.pdf` (0 extractable chunks — documents pypdf limit),
  `corrupt_invalid.pdf` (validation-test input). Generator: `tests/data/corpus/generate_corpus.py`.
- `pyproject.toml` sets pytest `testpaths=["tests"]`, ruff `target-version="py311"`,
  line-length 120. Config `workflow.nyquist_validation` is `false` → no Validation
  Architecture section required.

### 1.5 Dependency reality [VERIFIED via requirements files + `pip show`/`pip list`]

| Package | requirements.txt pin | Actually installed | Verdict |
|---|---|---|---|
| `streamlit` | `==1.42.0` | **1.65.0** | Pin is stale; code runs on 1.65.0. Do not downgrade. |
| `pypdf` | `==5.3.0` | **6.12.1** | Stale pin; `pypdf.PdfReader` API used here is stable across both. |
| `langchain-text-splitters` | `==0.3.6` | **1.1.3** | Stale pin; `RecursiveCharacterTextSplitter` kwargs unchanged. |
| `sentence-transformers` | `==3.4.1` | (present, version not re-checked) | Unchanged. |
| `pydantic` | **absent** | **2.11.9** (+ `pydantic_core` 2.33.2) | Must add to requirements.txt. PyPI latest 2.14.0; 2.11.9 is current enough — pin `pydantic==2.11.9`. |
| `SQLAlchemy` 2.0.49, `aiosqlite` 0.22.1 | absent | present in env (transitive/devenv) | Do NOT adopt; stdlib `sqlite3` suffices (see §2). |
| Python | 3.11+ (docs) | **3.13.5** | Pydantic v2 supports 3.8–3.13; no compat issue. Note ruff targets py311 — stay within 3.11-compatible syntax. |
| SQLite | stdlib | **3.49.1** (`sqlite3.sqlite_version`) | Modern; supports WAL, UPSERT, STRICT tables, JSON1. |

**Action:** Phase 1 adds exactly one dependency line (`pydantic==2.11.9`). Everything else
uses the standard library (`sqlite3`, `hashlib`, `pathlib`, `os`).

## 2. Key Decisions (recommendations — planner locks these)

### D1. Pydantic v2 API (not v1) [VERIFIED: pydantic 2.11.9 installed]

- Use v2-native syntax: `class M(BaseModel)` + `Field(...)`, `@field_validator`,
  `@model_validator`, `model_dump()` / `model_dump_json()` / `model_validate()`.
  Never `dict()`, `.parse_obj`, or `class Config` — those are v1 shims (v1 compat
  still importable in 2.x but deprecated and slower).
- `model_config = ConfigDict(frozen=True)` on value objects (BBox, Chunk) so chunks are
  hashable and safe to pass through the embedding pipeline; mutable roots (Document)
  stay unfrozen with explicit status-transition methods.
- Unknown-field policy: `model_config = ConfigDict(extra="forbid")` on `Document`/`Chunk`
  to catch schema drift early; `extra="allow"` is forbidden (hides Phase 3/4 field
  mismatches until runtime).

### D2. sqlite3 stdlib, NOT SQLAlchemy / aiosqlite

| Option | Verdict | Rationale |
|---|---|---|
| `sqlite3` stdlib | **USE** | Zero new deps; ACID via `commit()`/WAL; Streamlit runs sync script — async buys nothing. |
| SQLAlchemy 2.0 | REJECT | ORM overhead for 3 tables; present in env only incidentally; adds version-pin burden. |
| aiosqlite | REJECT | Async driver for a sync Streamlit script; thread-marshalling adds failure modes. |

- Connection lifecycle (critical, see §3 R1): **open → execute → commit → close per
  operation** (short-lived `sqlite3.connect()` inside a context manager in `DocStore`
  methods). Never cache a connection in `st.session_state` or `@st.cache_resource`
  (stale locks across reruns). SQLite connection setup is sub-millisecond locally —
  no pooling needed for single-user upload cadence.
- Concurrency: enable `PRAGMA journal_mode=WAL` + `busy_timeout=5000` at connect;
  single-writer (upload loop) + readers (chat path) is safe under WAL.
- Schema evolution: `PRAGMA user_version = 1` integer + `CREATE TABLE IF NOT EXISTS`;
  a `_migrations` map `{version: [DDL...]}` in `doc_store.py` applies incremental
  `ALTER TABLE` on open. Forward-compat columns (`bbox_json TEXT NULL`,
  `embedding_model TEXT NULL`) are created nullable in v1 so Phase 3/4 fill them later.

### D3. Canonical schema shapes (forward-compatible with Phase 3 Docling/OCR + Phase 4 LanceDB)

```python
# models.py — Pydantic v2. Target: pydantic==2.11.9 [ASSUMED field details; wire shapes locked below]
class BBox(BaseModel):  # frozen value object; None == "no geometry yet" (pypdf Phase 1)
    model_config = ConfigDict(frozen=True)
    x0: float; y0: float; x1: float; y1: float
    page_width: float | None = None; page_height: float | None = None

class Chunk(BaseModel):  # frozen; model_dump() must equal legacy keys content/filename/page/chunk_id
    model_config = ConfigDict(frozen=True)
    content: str = Field(min_length=1); filename: str; page: int = Field(ge=1)
    chunk_id: str  # "{sha256[:12]}_p{page}_{j}" — stable across renames (INGEST-02)
    doc_id: str; char_start: int | None = None; char_end: int | None = None
    bbox: BBox | None = None            # filled by Phase 3 (Docling); None until then
    extraction: str = "pypdf"           # provenance: pypdf | docling | rapidocr (Phase 3 extends Literal)
    embedding_model: str | None = None  # filled by Phase 4; None until then

class Page(BaseModel):
    doc_id: str; page_num: int = Field(ge=1); status: str = "ok"  # ok | empty | failed (INGEST-05)
    char_count: int = 0; error: str | None = None; num_chunks: int = 0

class EvidenceElement(BaseModel):  # minimal Phase 1 shell; Phase 3/5 extend
    element_id: str; doc_id: str; page: int = Field(ge=1); kind: str = "text"
    content: str; bbox: BBox | None = None; source: str = "pypdf"

class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str            # "doc_" + sha256(bytes)[:16] — filename-independent (INGEST-02)
    filename: str; sha256: str = Field(pattern=r"^[0-9a-f]{64}$"); size_bytes: int = Field(ge=0)
    num_pages: int = Field(ge=0); status: str = "indexed"  # pending | indexed | failed
    upload_time: str; num_chunks: int = 0
```

- SQLite tables mirror this 1:1: `documents(doc_id PK, filename, sha256 UNIQUE, size_bytes,
  num_pages, status, upload_time, num_chunks)`, `pages(doc_id, page_num, status, char_count,
  error, num_chunks; PK(doc_id, page_num))`, `chunks(chunk_id PK, doc_id, filename, page,
  content, char_start, char_end, bbox_json NULL, extraction, embedding_model NULL)`.
- `chunk_id` MUST change derivation from `{filename}_p{page}_{j}` to `{sha12}_p{page}_{j}`:
  filename-derived IDs break dedup-on-rename (INGEST-02). Keep `filename` as a column for display.
- Phase 4 `RetrievalResult` consumes `Chunk` via `model_dump()` — no re-modeling needed.

### D4. SHA-256: streaming hash over raw bytes, before any parsing

```python
# upload_validation.py
h = hashlib.sha256()
for offset in range(0, len(raw), 1024 * 1024): h.update(raw[offset:offset + 1024*1024])
digest = h.hexdigest()  # doc_id = "doc_" + digest[:16]
```

- Hash the `UploadedFile.getvalue()` bytes once; reuse the same bytes object for
  magic-byte check, size check, and `BytesIO` parsing — never call `getvalue()` twice
  (it copies). 1 MiB update slices keep peak memory flat for large PDFs (§3 R3).
- `doc_id = "doc_" + sha256[:16]` (16 hex chars ≈ 64-bit; collision risk negligible for
  single-user corpus) [ASSUMED — planner confirms length; 64-bit truncation is standard
  practice for non-adversarial dedup].

### D5. Disk cache layout (STORE-03)

```
.cache/
  {sha256}/
    {config_version}/
      pages.json        # Page[] dump
      chunks.json       # Chunk[] dump
      manifest.json     # {doc_id, config_version, created_at, chunker, embedding_model}
```

- `config_version = "chunker-{size}-{overlap}-{extraction}"`, e.g.
  `"chunker-1000-200-pypdf"`. Any chunker/extractor change → new version string →
  old cache ignored (no invalidation logic needed in Phase 1).
- Cache is keyed by full sha256 (dir name), chunk_id uses the 12-char prefix — no conflict.
- Windows-safe: hex-only names, no colons/spaces; use `pathlib.Path` throughout.

### D6. Streamlit progress idioms (extend `main.py`, don't reinvent)

- Keep `st.status(...)` + `st.write(...)` per stage + `.update(state="complete")` —
  matches `main.py:95-97,123-161`. Add three staged writes per file:
  `Validating → Extracting (page i/n via st.progress) → Indexing`.
- Use `st.progress(0..1)` for the page loop (new — fine inside `st.status`), and
  `st.error/st.success` per file preserving isolate-and-continue (`main.py:133-138`).
- Dedup hit path: `st.info(f"Already indexed ({doc_id}) — skipped.")`; validation failure:
  `st.error` + `continue`. Never `st.stop()` inside the loop (would abort sibling files).

## 3. Risks & Pitfalls

- **R1 — Stale SQLite connections across reruns (HIGH risk).** Streamlit reruns the whole
  script per interaction; a connection object cached in session state holds locks across
  reruns and breaks on Windows file locking. *Mitigation:* per-operation connect/close;
  add a regression test that opens two `DocStore` instances and interleaves writes.
- **R2 — `check_same_thread` violations.** Never share a connection across threads;
  `@st.cache_resource` on a store holding a connection is forbidden. Per-operation
  connections sidestep this entirely.
- **R3 — Large-PDF memory blowup.** `getvalue()` copies bytes; hashing + BytesIO + pypdf
  can triple peak RAM. *Mitigation:* single `getvalue()` call, 1 MiB hash slices,
  enforce `MAX_FILE_MB` (default 50 [ASSUMED — planner confirms]) and `MAX_PAGES`
  (default 500 [ASSUMED]) BEFORE parsing; reject oversize with `st.error`, never attempt.
- **R4 — Magic-byte bypass via polyglots.** `type=["pdf"]` + `%PDF` header check stops
  casual mis-uploads only. Check first 5 bytes `== b"%PDF-"` AND parse with pypdf inside
  try/except; treat `PdfReadError`/empty-pages as validation failure, not crash.
- **R5 — Windows paths.** Temp/cache paths via `pathlib`; never split on `/` (the
  `pdf_reader.py:19` basename hack breaks on `\` — replace with `Path(name).name`).
  `NamedTemporaryFile(delete=False)` needs explicit `os.unlink` cleanup after indexing.
- **R6 — Schema migration without data loss.** Raw `DROP TABLE` on model change destroys
  history. *Mitigation:* `user_version`-gated incremental migrations + `Strict`
  JSON round-trip tests (`model_dump_json` → `model_validate`).
- **R7 — Chunk-ID format change orphans session state.** Old `indexed_files` (filenames)
  vs new doc_ids. *Mitigation:* one-time migration — on first run with the store, treat
  `indexed_files` as empty and re-index; document in plan.

## 4. Recommended Approach

### 4.1 File layout (flat, one class per file — repo convention)

| File | Contents | Plan |
|---|---|---|
| `models.py` (new) | `BBox`, `Chunk`, `Page`, `EvidenceElement`, `Document` + `CONFIG_VERSION` const | 01-01 |
| `doc_store.py` (new) | `DocStore(db_path)` — per-op connections, WAL, CRUD, `user_version` migrations | 01-01 |
| `upload_validation.py` (new) | `validate_pdf_bytes(raw, filename)` → `ValidatedUpload`; `sha256_bytes()`; caps | 01-02 |
| `pdf_reader.py` (edit) | Per-page try/except → `Page(status=failed)`; emit `Chunk` via `Chunk(...)` then `model_dump()`; `Path(name).name` | 01-01 + 01-02 |
| `main.py` (edit) | Validate → dedup via `DocStore.get_by_sha` → staged `st.status`/`st.progress` → persist → `build_index` | 01-02 |
| `requirements.txt` (edit) | Add `pydantic==2.11.9` (only new dep) | 01-01 |
| `tests/test_models.py`, `test_doc_store.py`, `test_upload_validation.py` (new) | Extend existing banner/`match=`/corpus patterns; `tmp_path` for SQLite | both |

### 4.2 Tracer-first slice (build this first, then flesh out)

One end-to-end path before anything else: upload `clean_digital.pdf` → magic-byte + size
check → SHA-256 → `Document` row in SQLite → `st.success(doc_id)` in sidebar. This single
slice proves the validation→model→store→UI contract; page loop, cache, and re-index
migration layer on afterwards. Suggested commit order: `models.py` + tests →
`doc_store.py` + tests → `upload_validation.py` + tests → `main.py` wiring.

### 4.3 Test strategy (extends `tests/` patterns, offline-only)

- `test_models.py`: Chunk `model_dump()` key-equality with legacy dict; frozen-hash check;
  `extra="forbid"` rejection; JSON round-trip; BBox-None default.
- `test_doc_store.py`: `tmp_path` SQLite; insert→get round-trip; sha UNIQUE violation on
  re-upload; page-failure record; `user_version` migration v1→v2 on a fixture DB;
  two-instance interleave (R1 regression).
- `test_upload_validation.py`: `%PDF` header accept; `corrupt_invalid.pdf` reject;
  oversize/over-page reject (synthetic bytes, no large fixtures); SHA-256 stability
  across filename rename (INGEST-02 core assertion).
- Reuse `mock_sentence_transformer` for any embedding-touching test; never load real
  `SentenceTransformer` in unit tests (GPU/slow).

## 5. Don't Hand-Roll

| Problem | Don't build | Use instead | Why |
|---|---|---|---|
| Schema validation | Custom dict-checking helpers | Pydantic v2 (`pydantic==2.11.9`) | Error messages, JSON, validators free; custom checks rot |
| ACID persistence | JSON files / pickle | `sqlite3` stdlib + WAL | Atomicity, UNIQUE enforcement, crash safety |
| PDF header sniffing | Extension allowlist | `raw[:5] == b"%PDF-"` + pypdf parse | Extensions lie; `corrupt_invalid.pdf` proves it |
| Content hashing | MD5 / filename hash | `hashlib.sha256` streaming | MD5 collides; filenames aren't content |
| Progress UI | Custom HTML/JS spinners | `st.status` + `st.progress` | Native, rerun-safe, matches `main.py` |

## Sources

- **Primary (HIGH):** direct `Read` of `main.py`, `pdf_reader.py`, `local_embedding.py`,
  `vector_index.py`, `local_llm.py`, `requirements.txt`, `pyproject.toml`,
  `requirements-test.txt`, all `tests/*.py`, REQUIREMENTS.md, ROADMAP.md, config.json;
  `pip show`/`pip list` output (pydantic 2.11.9, SQLite 3.49.1, Streamlit 1.65.0,
  Python 3.13.5) — all executed this session.
- **Secondary (MEDIUM):** Pydantic v2 / sqlite3-WAL / Streamlit `st.status`+`st.progress`
  idioms are stable, long-documented APIs — no version risk identified.
- **[ASSUMED] items needing planner/user lock:** `MAX_FILE_MB=50`, `MAX_PAGES=500`,
  `doc_id` 16-hex-char truncation, `chunker-1000-200-pypdf` version string format.
  None affect library choice.

## Metadata

- Standard stack: HIGH — installed versions verified, single new dep.
- Architecture: HIGH — derived verbatim from source reads.
- Pitfalls: HIGH — R1/R3/R5 grounded in `main.py`/`pdf_reader.py` code paths.
- Valid until: 30 days (stable domain; only dep watch is `pydantic` 2.14.0 release).
