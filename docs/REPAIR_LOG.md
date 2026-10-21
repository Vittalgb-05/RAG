# Repair Log

**Date:** 2026-10-21
**Baseline:** `dc701ec` — 296 tests passing, Ruff clean.
**Policy:** one atomic commit per root-cause group; no destructive migration; no cloud egress; preserve `data/`, `models/`, and legacy index files.

## Commit sequence

| Commit | Subject | Root cause | Fix | Verification |
|---|---|---|---|---|
| `a6dc76a` | `fix(data): use canonical LanceDB path and fail loudly on index loss` | `DEFAULT_DB_URI` pointed at `retrieval/data/lancedb`; vector write/delete failures were swallowed | Canonical `data/lancedb`; non-destructive legacy migration; `VectorIndexError`; vectors-first delete; verified reindex; atomic ingestion call | Retriever and audit tests; 309-suite green |
| `7044982` | `fix(storage): make ingestion atomic and invalidate legacy summaries` | Document/pages/chunks/evidence committed separately; empty summary version treated as valid; UI fell back to version-agnostic cache | `DocStore.record_ingestion` single transaction; empty version is stale; strict UI lookup; `get_pages_for_doc` | Doc-store, cache-invalidation, audit tests |
| `5c50656` | `fix(ingestion): bound summarization prompts and preserve table structure` | Map-reduce could exceed 4,096 tokens; long tables went through prose splitter; Docling could take GPU | 2,000-token fast path; 2,500-token consolidation; oversized-page splitting; header-repeating table splitter; offset clamping; CPU pinning; `DOCLING_ARTIFACTS_PATH` | Summarizer, Docling, audit tests |
| `c3518ce` | `fix(privacy): require explicit consent for cloud routing` | `AiModel(cloud_mode=True)` silently built `GroqProvider`; Groq had no consent gate; duplicate health probes | Consent requirement and `PermissionError`; gated generate/stream/vision; single probe; 5 s UI health cache | Local-LLM, Groq, cloud-privacy, main-UI tests |
| `53caa80` | `fix(privacy): block bare URLs and media embeds in local mode` | Sanitizer missed bare URLs, autolinks, reference definitions, and several embed/form tags | Added URL/reference neutralization and expanded unsafe tag set | Sanitizer and audit tests |
| `e75733c` | `fix(setup): harden downloads and verify GGUF identity` | `extractall` traversal risk; no checksum/GGUF validation; labels claimed Qwen3 | Safe archive extraction; optional SHA-256; GGUF magic + metadata parser; launch refusal on mismatch; `qwen2-vl-2b` provider id | Setup, launcher, provider, identity tests |
| `f33a6dc` | `docs: correct model identity to Qwen2-VL 2B` | Filename/labels/docstrings claimed Qwen3-VL while weights are Qwen2-VL | Corrected prose labels; retained legacy filename with explanation | GGUF metadata + grep review |
| `90e22a9` | `test: cover audit regressions across storage, privacy, and identity` | Repairs lacked durable regression coverage | 13 targeted tests | 309 passed |
| pending docs commit | Audit deliverables and setup/architecture notes | Audit evidence was not recorded in-repo | Added audit docs, updated README/runbooks/requirements | Markdown review |

## Detailed root causes

### 1. Vector index path divergence (P0)

- **Symptom:** Documents appeared ingested but were unsearchable after restart.
- **Cause:** `HybridRetriever.DEFAULT_DB_URI` was `Path(__file__).parent / "data" / "lancedb"`, i.e. `retrieval/data/lancedb`; runtime data lived in repo `data/lancedb`.
- **Repair:** Path now resolves to repo root `data/lancedb`. If a legacy package-relative index exists and the canonical target has no `*.lance`, it is copied. The source is never deleted.
- **Evidence:** `test_default_index_lives_under_repo_data_directory`, `test_legacy_package_relative_index_is_copied_non_destructively`.

### 2. Silent vector loss (P0)

- **Symptom:** `index_chunks` returned the number of chunks even when LanceDB persistence failed.
- **Cause:** broad `except Exception` logged and continued.
- **Repair:** Save the fallback store, log the failure, raise `VectorIndexError`. Callers now mark the document failed and do not claim success.
- **Evidence:** `test_index_chunks_raises_instead_of_silently_claiming_success`.

### 3. Non-atomic ingestion (P0)

- **Symptom:** A crash mid-ingestion could leave document metadata without pages/chunks, or vice versa.
- **Cause:** `upsert_document`, `record_pages_batch`, `record_chunks`, `record_evidence_elements` each committed independently.
- **Repair:** `record_ingestion` deletes stale children and writes document/pages/chunks/evidence in one transaction with rollback.
- **Evidence:** `test_record_ingestion_replaces_stale_children_atomically`.

### 4. Delete/purge lying about success (P0)

- **Cause:** vector and cache exceptions were logged and ignored; SQLite was deleted first.
- **Repair:** delete vectors first (abort on failure), then SQLite, then cache. Purge collects per-tier failures and raises `RuntimeError("Purge incomplete …")`; session state still clears.
- **Evidence:** `test_lifecycle_delete_aborts_before_sqlite_on_vector_failure`, `test_purge_reports_vector_failure_but_clears_session_state`.

### 5. Summary cache staleness (P1)

- **Cause:** empty legacy `model_version` was accepted; UI fell back to version-agnostic lookup.
- **Repair:** strict version match; empty version is stale; UI passes `model:CONFIG_VERSION` only.
- **Evidence:** `test_summary_cache_rejects_empty_legacy_version`, cache-invalidation suite.

### 6. Prompt-budget overflow (P1)

- **Cause:** 2,500-token fast path + system + 1,500 output exceeded 4,096; consolidation split only into two halves; a single oversized page could not split.
- **Repair:** 2,000-token fast path; 2,500-token consolidation input; `_split_oversized_pages`; iterative `_consolidate_summaries`.
- **Evidence:** `test_summarizer_splits_oversized_page_into_bounded_batches`, summarizer suite.

### 7. Table structure loss (P1)

- **Cause:** tables longer than 2,000 chars were passed to the prose splitter; offsets could exceed page text.
- **Repair:** `_split_table_markdown` splits by rows and repeats the header; offsets clamped.
- **Evidence:** `test_long_markdown_table_split_repeats_header`, Docling suite.

### 8. Cloud consent bypass (P0)

- **Cause:** `AiModel._detect_provider()` constructed `GroqProvider()` whenever `cloud_mode=True`; Groq had no consent check.
- **Repair:** constructor and `set_cloud_mode(True)` require a `user_consented=True` provider; Groq generation/stream/vision call `_assert_consent()`.
- **Evidence:** consent tests in local-LLM, Groq, cloud-privacy, and audit suites.

### 9. Sanitizer egress gaps (P0)

- **Cause:** only explicit Markdown links and a small tag list were handled.
- **Repair:** bare URLs, autolinks, reference definitions, and `video/audio/source/track/form/input/button/base/meta/link` tags are neutralized in local mode.
- **Evidence:** sanitizer and audit tests.

### 10. Resource and startup defects (P1)

- Docling forced to CPU; health probed once; UI probe cached 5 s; hydration marks complete only after success and isolates per-document repair; reindex deletes stale vectors and verifies `has_document`.
- **Evidence:** Docling, local-LLM, hydration, main-UI, audit suites.

### 11. Supply-chain and identity defects (P1)

- Safe zip/tar extraction (no traversal, no links); optional SHA-256; GGUF magic check; GGUF metadata parser; launcher refuses mismatched LM/projector.
- **Evidence:** setup tests, launcher tests, identity test on installed artifacts.

## Data safety

No runtime data was removed or migrated destructively. The legacy index migration is copy-only. `data/documents.db`, `data/lancedb/`, `.cache/`, and both GGUF files remain in place. The only new files are source, tests, and documentation.

## Rollback

Each commit is independent and can be reverted individually:

```bash
git revert <commit>   # e.g. a6dc76a for the path/failure semantics
```

Reverting the data commit alone restores the previous path/failure behavior but leaves the regression tests failing; revert the test commit (`90e22a9`) first if a full rollback is intended.

## Residual work

Live inference, GPU VRAM, OCR/VLM quality, and restart persistence against real documents remain manual checks (see `TEST_RESULTS.md` §4 and `AUDIT_SUMMARY.md` §6).
