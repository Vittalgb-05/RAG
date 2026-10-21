# Full Repository Audit — Summary

**Date:** 2026-10-21
**Repository:** Local-First Multimodal PDF Intelligence System
**Branch:** `main`
**Audit baseline:** `dc701ec` (296 tests passing, Ruff clean)
**Final commit under audit:** see `git log --oneline dc701ec..HEAD`
**Verdict:** **RUNNABLE FOR LOCAL TESTING**
**Not yet:** **READY FOR PERSONAL USE** — live llama-server, GPU/VRAM, and real-document runs could not be executed in this environment (no server was running). Those checks are explicitly marked **UNTESTED** below and in `TEST_RESULTS.md`.

---

## 1. Scope

The audit covered every Python module, test suite, configuration file, model artifact, and architecture/setup document. It verified:

- Ingestion → storage → indexing → retrieval → generation → citation flow.
- Local-first privacy guarantees and cloud consent boundaries.
- Persistence correctness across SQLite, LanceDB, and the on-disk extraction cache.
- 4 GB VRAM safety assumptions (CPU pinning, serialized inference, prompt budgets).
- Windows launcher and setup/download hardening.
- Model artifact identity versus filenames, labels, and documentation.

Out of scope: destructive data migration, changing the UI visual language, downloading new model weights, and transmitting any document content to a cloud provider.

## 2. Verification environment

| Item | Value |
|---|---|
| OS | Windows 11, PowerShell + Git Bash |
| Python | 3.13.5 |
| Key packages | Streamlit 1.42.0, LanceDB 0.40.0, Docling 2.140.0, RapidOCR 3.10.0, PyMuPDF 1.28.2, sentence-transformers 3.4.1, torch 2.6.0+cu124, pytest 9.0.3, Ruff 0.15.12 |
| Models present | `models/qwen3-vl-2b-instruct-q4_k_m.gguf` (986,047,232 B), `models/mmproj-f16.gguf` (1,331,656,192 B) |
| Actual model identity | GGUF metadata: `general.architecture=qwen2vl`, `general.name=Qwen2 VL 2B Instruct`, projector `qwen2vl_merger` |
| llama-server | **Not running**; `127.0.0.1:8080/health` and `/v1/models` timed out |
| Runtime data | `data/documents.db`, `data/lancedb/`, `.cache/` preserved; no data deleted |

## 3. Findings by severity

### P0 — data loss, false success, or privacy breach

| ID | Finding | Impact | Resolution |
|---|---|---|---|
| P0-1 | `DEFAULT_DB_URI` resolved to `retrieval/data/lancedb`, while the real index lives in `data/lancedb` | All persisted vectors invisible after restart; hydration/ingestion could silently rebuild or fail | Canonical repo-root path, non-destructive legacy migration, regression test |
| P0-2 | `index_chunks` swallowed LanceDB write failures and returned the input count | Ingestion reported success with zero searchable vectors | Raises `VectorIndexError`, always writes durable fallback store |
| P0-3 | Ingestion wrote document/pages/chunks/evidence in separate commits | Partial documents after any mid-ingestion failure | New single-transaction `DocStore.record_ingestion` with stale-child cleanup |
| P0-4 | Delete/purge swallowed vector failures after deleting SQLite rows | Orphaned vectors and “successful” deletes that reappear as broken docs | Vectors deleted first; failures abort delete; purge reports incomplete tiers |
| P0-5 | Re-index never deleted stale vectors and never verified writes | Duplicate/stale chunks; silent empty index | Delete-before-index plus `has_document` verification |
| P0-6 | Cloud mode could silently construct `GroqProvider` without consent; Groq calls had no gate | Document text could leave the machine without explicit consent | `PermissionError` unless a `user_consented=True` provider is supplied; all Groq generation/vision gated |
| P0-7 | Local sanitizer missed bare URLs, autolinks, reference definitions, and media/form embeds | Markdown/HTML could trigger outbound requests in local mode | Pattern-based neutralization for all discovered forms |

### P1 — correctness, bounded-resource, or reproducibility defects

| ID | Finding | Resolution |
|---|---|---|
| P1-1 | Summary cache fell back to a version-agnostic lookup; empty legacy versions were accepted | Version-aware lookup only; empty version is stale |
| P1-2 | Map-reduce could exceed the 4,096-token context (2,500-token fast path + system + 1,500 output; 2-way consolidation; unsplittable pages) | 2,000-token fast path, 2,500-token consolidation input, oversized-page splitting, iterative bounded reduction |
| P1-3 | Long Docling tables were sent through the prose splitter and lost headers | Row-aware `_split_table_markdown` repeats the header; offsets clamped |
| P1-4 | Docling defaulted to `AcceleratorDevice.AUTO` and could contend for VRAM | CPU device pinned; `DOCLING_ARTIFACTS_PATH` supported |
| P1-5 | Health check probed the same provider twice on failure; UI probed every rerun | Single probe; UI probe throttled to 5 s and invalidated on provider change |
| P1-6 | Hydration marked startup complete before work and aborted all docs on one repair failure | Completion set only after success; per-document failure isolation with retry |
| P1-7 | Setup used `extractall` without traversal checks, checksum verification, or GGUF validation | Safe extractor, optional SHA-256, GGUF magic + metadata verification |
| P1-8 | Model labels/filenames claimed Qwen3-VL while weights are Qwen2-VL | GGUF identity parser, launch refusal on mismatch, docs and labels corrected (legacy filename retained) |

### P2 — quality and maintainability

- `retrieval/vector_index.py` remains as a legacy in-memory fallback with overlapping responsibilities; documented as fallback-only.
- Benchmark/evaluation numbers were produced against the previous label and were not re-run on this hardware. Treat them as historical, not current evidence.
- CI pins Python 3.11 while the audit host runs 3.13.5; both must stay green.
- No automated live-server integration suite exists; endpoint checks are manual and currently **UNTESTED**.

## 4. What changed

Eight atomic commits (plus this documentation and regression tests), summarized in `REPAIR_LOG.md`:

1. Canonical LanceDB path, loud index failures, vector-first lifecycle, atomic ingestion.
2. Atomic SQLite ingestion and version-correct summary caching.
3. Bounded summarization and structure-preserving table chunking; Docling CPU pinning.
4. Explicit cloud consent; single-probe health; throttled UI health checks.
5. Local-mode egress hardening in the sanitizer.
6. Download/extraction hardening and GGUF identity verification.
7. Model identity documentation corrections.
8. Thirteen regression tests spanning all repaired root causes.

## 5. Evidence

| Gate | Result |
|---|---|
| `python -m pytest -q --no-header` | **309 passed**, 0 failed, 0 skipped (39.7–44.4 s across final runs) |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 72 files already formatted |
| GGUF identity | `qwen2vl` LM + `qwen2vl_merger` projector; verifier returns `[]` |
| Default index path | `C:\Users\OM Prakash\Documents\RAG\data\lancedb` (test-asserted) |
| Live `/health` | **UNTESTED** — connection timeout |
| Live text/vision inference | **UNTESTED** — no llama-server |
| Real RTX 3050 VRAM peak | **UNTESTED** — no live inference |

## 6. Verdict and remaining path to READY FOR PERSONAL USE

**RUNNABLE FOR LOCAL TESTING** is justified: the application imports, the full unit/contract suite passes, the launcher validates artifacts before starting, and no known P0 defect remains in the static/runtime paths exercised by tests.

To reach **READY FOR PERSONAL USE**, a human must run the following on the target RTX 3050 machine:

1. `python setup.py download_models` (or verify existing artifacts) then `python setup.py install_llama`.
2. `python start.py --start-llama` and confirm `/health` returns ready.
3. Ingest `tests/data/corpus/clean_digital.pdf`, `dense_table.pdf`, `scanned_sample.pdf`, and `chart_diagram.pdf`.
4. Restart Streamlit and confirm all documents still answer with citations (persistence check).
5. Delete one document, re-index another, then purge all; confirm SQLite/LanceDB/cache agree.
6. Ask an unanswerable question and confirm explicit abstention; ask a grounded question and confirm `[E#]` citations resolve.
7. Enable Cloud Mode without consent and confirm it is refused; then consent explicitly and confirm the privacy warning.
8. Record peak VRAM and latency against `docs/EVALUATION.md`; update stale figures if they differ.

Until these are executed and recorded, the correct status is **RUNNABLE FOR LOCAL TESTING**, not personal-use ready.
