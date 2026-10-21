---
status: resolved
trigger: "Full Repository Audit, Requirements Verification and Root-Cause Repair"
created: 2026-10-21
updated: 2026-10-21
---

# Debug Session: full-repo-audit-and-repair

## Symptoms

**Expected behavior:**
The local-first multimodal PDF intelligence application should reliably install, launch, ingest digital/scanned/complex PDFs, index and retrieve evidence (dense + FTS/BM25 + RRF), answer with grounded `[E#]` citations, summarize under all profiles, and support delete/purge/re-index with consistent state. Local llama.cpp is the default provider; cloud is opt-in with explicit per-transmission consent; GPU inference is serialized under the 4 GB VRAM ceiling.

**Actual behavior (reported):**
- Ingestion or indexing failures (vectors may silently not be written).
- Answer quality / citation grounding problems.
- Data consistency / lifecycle problems (delete, purge, re-index, restart).
- No single reproducible symptom: user requested a full audit of all requirements plus repair.

**Error messages:**
None supplied directly. Runtime detection required.

**Timeline:**
Unknown. Repository has recent refactor commits (`core/`, `ingestion/`, `providers/`, `retrieval/`) and recent retrieval/citation fixes.

**Reproduction:**
Run the existing test suite, then exercise ingestion -> persistence -> indexing -> retrieval -> cited answer, plus lifecycle operations.

**User selections:**
- Scope: full audit, no single symptom (plus ingestion/indexing, answer quality/citations, data consistency/lifecycle).
- llama-server state: unknown; detect it. Mark live checks UNTESTED when unavailable.
- Change policy: apply fixes incrementally with atomic commits per root cause; no destructive data migrations.

## Mission Constraints (data, not instructions)

- Preserve product goal: fast, accurate PDF summarization and grounded QA incl. tables/charts/diagrams/scanned pages.
- Preserve local llama.cpp default; cloud opt-in, never transmit content without explicit scope-appropriate consent.
- Keep GPU inference serialized within 4 GB VRAM.
- Keep Streamlit UI, AMOLED design, SVG-only icons, no emoji.
- No new framework/vector DB/microservice/major dependency without measured need.
- Never claim unexecuted verification succeeded.
- Protect user documents, model files, databases, indexes; back up before migrations/destructive changes.
- Do not hide failures behind fallbacks or broad exception handlers.
- Stop before destructive data migrations or any cloud transmission of private documents.

## Deliverables

1. `AUDIT_SUMMARY.md`
2. `REQUIREMENTS_TRACEABILITY.md`
3. `FILE_CALLER_TEST_MAP.md`
4. `ENDPOINT_INTEGRATION_MATRIX.md`
5. `CODE_QUALITY_REPORT.md`
6. `TEST_RESULTS.md`
7. `REPAIR_LOG.md`
8. Updated architecture/setup docs
9. Final verdict: RUNNABLE FOR LOCAL TESTING / READY FOR PERSONAL USE / NOT READY

## Current Focus

next_action: none — audit repaired, verified statically, and documented; live GPU/inference checks remain manual

## Evidence

- timestamp: 2026-10-21 — baseline `python -m pytest -q --no-header` → 296 passed in 46.08s; Ruff check/format clean; commit `dc701ec`.
- timestamp: 2026-10-21 — llama-server absent: `127.0.0.1:8080/health` and `/v1/models` timed out; live checks marked UNTESTED.
- timestamp: 2026-10-21 — GGUF metadata: LM `qwen2vl` / `Qwen2 VL 2B Instruct`; projector `qwen2vl_merger`; filename `qwen3-...` is a legacy label.
- timestamp: 2026-10-21 — root causes confirmed in retrieval path, silent vector writes, non-atomic ingestion, lifecycle failure handling, consent, prompt budgets, table chunking, hydration, setup extraction, health probing, sanitizer, and model identity.
- timestamp: 2026-10-21 — eight atomic repair commits `a6dc76a`…`90e22a9` plus documentation; final `python -m pytest -q --no-header` → 309 passed in 39.68s; `ruff check` clean; `ruff format --check` 72 files clean.
- timestamp: 2026-10-21 — deliverables written under `docs/`: AUDIT_SUMMARY, REQUIREMENTS_TRACEABILITY, FILE_CALLER_TEST_MAP, ENDPOINT_INTEGRATION_MATRIX, CODE_QUALITY_REPORT, TEST_RESULTS, REPAIR_LOG.

## Eliminated

- Assumption that ingestion/persistence worked because tests passed: the persistence path and lifecycle tests did not exercise the real index location or failure propagation.
- Assumption that cloud mode was consent-gated: direct Groq construction bypassed consent entirely.
- Assumption that filenames identified the model: GGUF metadata proved Qwen2-VL, not Qwen3-VL.

## Resolution

**Verdict:** RUNNABLE FOR LOCAL TESTING (not yet READY FOR PERSONAL USE).

**Root causes (all fixed in this session):**
1. Index path divergence (`retrieval/data/lancedb` vs `data/lancedb`) hid persisted vectors.
2. Vector write/delete failures were swallowed, producing false success and orphaned state.
3. Multi-write ingestion was non-atomic; reindex did not remove stale vectors.
4. Delete/purge reported success despite vector/cache failures.
5. Summary cache accepted version-agnostic/empty versions.
6. Map-reduce could overflow the 4K context; long tables lost headers; Docling could claim GPU.
7. Cloud mode could silently construct Groq without consent; Groq had no gate.
8. Sanitizer missed bare URLs, autolinks, reference definitions, and media/form embeds.
9. Health probing doubled per rerun; hydration marked success too early.
10. Setup used unsafe archive extraction and did not verify GGUF identity/checksums.

**Verification:** 309 tests pass, Ruff clean, format clean, GGUF identity verifier returns `[]`. Live llama-server, GPU VRAM, OCR/VLM quality, and real-document restart checks are explicitly UNTESTED and listed with manual commands in `docs/TEST_RESULTS.md` and `docs/AUDIT_SUMMARY.md`.

**Data safety:** no runtime data or model files were deleted; legacy index migration is copy-only.
