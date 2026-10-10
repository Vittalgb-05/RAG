---
phase: 01-canonical-document-models
plan: 01-01
status: completed
key_files:
  created:
    - models.py
    - doc_store.py
    - tests/test_models.py
    - tests/test_doc_store.py
  modified:
    - pdf_reader.py
    - requirements.txt
    - README.md
requirements_covered:
  - STORE-02
  - STORE-01
  - STORE-03
---

# Phase 1 Plan 01-01 Summary: Canonical Pydantic Schemas & SQLite Metadata Store

## Overview
Replaced volatile session dictionaries and untyped chunk dicts with typed, immutable Pydantic v2 schemas and an ACID SQLite metadata store that persists across application restarts. Legacy consumers (`VectorIndex`, `LocalEmbedding`, and `main.py`) remain 100% backward-compatible via `Chunk.model_dump()`.

## Accomplished Tasks

1. **Canonical Pydantic v2 Models (`models.py`, STORE-02):**
   - Implemented `BBox` (frozen), `Chunk` (frozen, extra=forbid), `Page` (extra=forbid), `EvidenceElement`, and `Document` (extra=forbid, sha256 pattern validation).
   - Ensured `Chunk.model_dump()` produces exact legacy keys (`content`, `filename`, `page`, `chunk_id`) with identical values.
   - Defined `CONFIG_VERSION = "chunker-1000-200-pypdf"` and `cache_dir_for` path computation helper.

2. **Model Contract Tests (`tests/test_models.py`):**
   - Verified immutability, hashing, extra-field forbidding, invalid SHA rejection, and JSON serialization.
   - Built the end-to-end tracer test `test_tracer_chunk_to_store_roundtrip` reading `clean_digital.pdf`, constructing canonical `Chunk`, persisting `Document` in SQLite via `DocStore`, and round-tripping.

3. **SQLite Metadata Store (`doc_store.py`, STORE-01):**
   - Implemented `DocStore` with per-operation connections, `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, and `PRAGMA user_version = 1` migrations.
   - Implemented CRUD methods: `upsert_document`, `get_document`, `get_by_sha`, `list_documents`, `record_page`, and `record_chunks`.
   - Forward-compatible nullable columns `bbox_json` and `embedding_model` for multimodal expansions.

4. **Persistence & Concurrency Regression Tests (`tests/test_doc_store.py`):**
   - Verified document round-trip, SHA uniqueness constraint, page extraction error recording, two-instance concurrency interleaving, schema versioning, and chunk storage.

5. **Producer Integration (`pdf_reader.py`, `requirements.txt`):**
   - Pinned `pydantic==2.11.9` in `requirements.txt`.
   - Updated `PdfReader` to extract filenames safely via `Path(file_or_path).name` and validate chunks through `Chunk.model_dump()`.

6. **Documentation & Migration Notes (`README.md`):**
   - Documented the transition to content-hash `doc_id` identity and the session state migration policy.

## Verification
- Test Suite: 35/35 tests passing (`pytest tests/ -v`)
- Linter & Formatting: Clean (`ruff check .`, `ruff format --check .`)
