---
phase: 01-canonical-document-models
reviewed: 2026-10-11T02:30:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - models.py
  - doc_store.py
  - upload_validation.py
  - pdf_reader.py
  - main.py
  - tests/test_models.py
  - tests/test_doc_store.py
  - tests/test_upload_validation.py
  - tests/test_pdf_reader.py
  - tests/conftest.py
  - requirements.txt
  - local_embedding.py
findings:
  critical: 3
  warning: 8
  info: 6
  total: 17
status: issues_found
verdict: NEEDS FIXES
---

# Phase 01: Code Review Report — Canonical Document Models

**Reviewed:** 2026-10-11T02:30:00Z
**Depth:** standard (per-file analysis, Python-specific checks)
**Files Reviewed:** 12 (7 in-scope new/modified + conftest.py, local_embedding.py, vector_index.py as compat spot-checks)
**Verdict:** NEEDS FIXES (3 Critical must be fixed before this ships as a persistence story)

## Summary

Phase 1 delivers clean, well-tested schema and validation code — `ruff check` passes on all
reviewed files and the model/dict-compat contract (`Chunk.model_dump()` legacy keys) is real.
But the end-to-end persistence story the phase claims is broken in three places: (1) the
dedup-hit path never restores embeddings, so after any restart every re-uploaded file is
skipped forever with chat permanently disabled; (2) the `PdfReader` constructor sits outside
any try/except in the upload loop, so one malformed-but-`%PDF`-headered file aborts the whole
batch; (3) `record_chunks` is never called in the production path, so the `chunks` table is
dead in prod and nothing can ever rebuild the index. Eight warnings (connection lifecycle,
fault-isolation scope, TOCTOU race, memory ordering, unvalidated identity fields, lexical
chunk ordering, write-never-read cache, timestamp inconsistency) and six info items follow.

## Critical Issues

### CR-01: Dedup-hit path never restores embeddings — restart leads to permanent dead end

**File:** `main.py:136-148`
**Category:** Correctness (data flow)
**Issue:** On a dedup hit (`doc_id in session OR DocStore row with status == "indexed"`),
the handler only updates display metadata and `continue`s. It never rebuilds
`st.session_state.local_embedding`. After a server restart the session index is `None`
(session state is volatile), so: every previously indexed file hits the DocStore branch,
is "skipped" as a duplicate, the embedding index stays `None`, chat stays disabled, and
the user has no in-UI path to ever query again short of wiping `data/documents.db`.
The plan-checker-flagged `dedup-hit-on-empty-index` issue is NOT fixed. Combined with
CR-03 (chunks table empty in prod) there is not even stored data to rebuild from.
**Fix:**
```python
# On dedup hit with empty session index, rebuild from persisted chunks:
if st.session_state.local_embedding is None:
    st.session_state.local_embedding = LocalEmbedding()
    for known_id in st.session_state.doc_ids:
        persisted = doc_store.get_chunks_for_doc(known_id)
        if persisted:
            st.session_state.local_embedding.build_index([c.model_dump() for c in persisted])
```
(requires CR-03 fixed first so chunks actually exist). At minimum, surface
`st.warning("Index is empty after restart — re-upload to re-index")` instead of a silent skip.

### CR-02: `PdfReader` construction outside try/except aborts entire batch on malformed PDF

**File:** `main.py:156-162`
**Category:** Correctness (error handling)
**Issue:** Only `validate_pdf_bytes` is wrapped (`try/except ValueError`, line 126-130).
`PdfReader(pdf_stream, ...)` calls `pypdf.PdfReader(file_or_path)` in its constructor
(`pdf_reader.py:16`), which raises on malformed/encrypted/trailer-broken PDFs even when
the `%PDF` magic-byte check passed. `test_pdf_reader_corrupt_pdf_rejects` proves the
constructor itself raises. One such file raises an uncaught exception, kills the whole
`for uploaded_file` loop, and surfaces a Streamlit exception page — violating the
isolate-and-continue contract (`st.error(...) then continue`) the phase claims for
per-document processing. Same gap covers `extract_text`/`split_text`/`Chunk(...)`
failures (see WR-02).
**Fix:**
```python
try:
    pdf_reader = PdfReader(pdf_stream, filename=filename)
    sha12 = validated.sha256[:12]
    pdf_reader.extract_text(doc_id=doc_id, sha12=sha12)
    paragraphs = pdf_reader.get_paragraphs()
    page_records = pdf_reader.get_page_records()
except Exception as err:
    st.error(f"Could not extract text from `{filename}` ({err})")
    continue
```

### CR-03: `record_chunks` never called in production path — `chunks` table dead in prod

**File:** `main.py:170-188`
**Category:** Correctness (persistence gap)
**Issue:** The upload flow calls `doc_store.record_page()` per page and
`doc_store.upsert_document()` once, but never `doc_store.record_chunks()`. The `chunks`
table (with its `bbox_json`/`embedding_model` forward-compat columns, tested only with
synthetic data in `test_chunk_json_columns_nullable`) is always empty in production.
Consequences: `get_chunks_for_doc()` returns `[]` for every real document, STORE-01's
"chunk persistence" is unproven outside unit tests, and no restart-rebuild path (CR-01)
is possible. The `.cache/chunks.json` dump is the only chunk record, and it is never
read back (WR-07).
**Fix:**
```python
from models import Chunk
doc_store.record_chunks([Chunk.model_validate(p) for p in paragraphs])
```
placed after `build_index`, inside the same per-file guard so a chunk-store failure
cannot orphan pages without a document row (or vice versa — wrap steps 5+6 in one try).

## Warnings

### WR-01: SQLite connections never closed — `with conn:` does not close

**File:** `doc_store.py:77-79, 127, 156, 176, 190, 214, 268, 282`
**Category:** Correctness (resource lifecycle)
**Issue:** Every method uses `with self._connect() as conn:`. A `sqlite3.Connection`
context manager only commits/rolls back on exit — it does **not** close the connection.
Under Streamlit's rerun-every-interaction model plus per-page `record_page` calls, file
descriptors and WAL handles accumulate until CPython refcount-GCs them, risking
`database is locked` errors on Windows (the exact failure mode the per-op-connection
design was meant to avoid).
**Fix:** Use `contextlib.closing`, or try/finally:
```python
from contextlib import closing
with closing(self._connect()) as conn:
    ...
    conn.commit()
```

### WR-02: Fault-isolation scope too narrow — `Chunk` validation errors abort whole document

**File:** `pdf_reader.py:48-105`
**Category:** Correctness (edge case)
**Issue:** The per-page `try/except` wraps only `page.extract_text()` (line 50-51).
The `text_splitter.split_text()` call and `Chunk(...)` construction (lines 83-93) sit
outside it. `Chunk.content` has `min_length=1`, and content is `p.strip()` — a
whitespace-only splitter output yields `""` and raises `ValidationError`, aborting the
entire document despite INGEST-05. Same for any splitter exception.
**Fix:** Extend the try to cover split + validate per page, recording
`Page(status="failed")` and `continue`-ing; or filter `if not p.strip(): continue`
before constructing `Chunk`.

### WR-03: Dedup check-then-insert TOCTOU race yields uncaught `IntegrityError`

**File:** `main.py:134, 188` + `doc_store.py:118-141`
**Category:** Correctness (concurrency)
**Issue:** `get_by_sha` (read) and `upsert_document` (write) are separate per-op
connections with no transaction spanning them. Two concurrent sessions uploading the
same file both miss the check, both insert, and the loser gets an uncaught
`sqlite3.IntegrityError` from the `UNIQUE(sha256)` constraint → Streamlit exception
page. The test suite pins the raise (`test_sha_unique_violation_on_reupload`) but no
caller handles it.
**Fix:** Wrap `doc_store.upsert_document(doc_model)` in `try/except sqlite3.IntegrityError`
mapping to the same dedup-hit UI path, or make the write idempotent on `sha256`.

### WR-04: Full file buffered in memory before the 50 MB size check runs

**File:** `main.py:121` + `upload_validation.py:79-84`
**Category:** Security (resource exhaustion)
**Issue:** `uploaded_file.getvalue()` copies the entire payload into RAM before
`validate_pdf_bytes` ever checks `len(raw) > MAX_FILE_MB*...`. A 500 MB upload is fully
resident before rejection. Streamlit's `getvalue()` API forces one copy, but the code
could check `uploaded_file.size` first and reject without ever reading bytes.
**Fix:**
```python
if uploaded_file.size is not None and uploaded_file.size > MAX_FILE_MB * 1024 * 1024:
    st.error(f"File too large ... — {filename}.")
    continue
raw_bytes = uploaded_file.getvalue()
```
(Note: `tests/test_upload_validation.py:54-58` also allocates ~51 MB in-process for the
oversize test — acceptable but slow; consider monkeypatching `MAX_FILE_MB` down instead.)

### WR-05: Identity fields unvalidated — `doc_id`/sha mismatch and free-form statuses accepted

**File:** `models.py:57, 74, 90, 104-109` + `upload_validation.py:35-45`
**Category:** Correctness (validation)
**Issue:** (a) `Document.doc_id` is a bare `str` with no cross-check against `sha256`
— a row with `doc_id="doc_deadbeef..."` + unrelated `sha256` validates fine, silently
breaking the `doc_ + sha[:16]` invariant every consumer assumes. (b) `doc_id_for()`
accepts any string (`doc_id_for("short")` → `"doc_short"`) with no 64-hex enforcement.
(c) `Page.status` / `Document.status` / `EvidenceElement.kind` are unconstrained `str`
— `"bogus"` passes validation; the `ok|empty|failed` contract lives only in docstrings.
**Fix:** Add `@field_validator`/`model_validator` for doc_id↔sha consistency (or derive
doc_id in the constructor), validate `sha` shape in `doc_id_for`, and use `Literal`
types for status/kind (plan claims enums would "break Phase 3" — `Literal` with a
commented extension point preserves that while rejecting typos today).

### WR-06: Lexical `chunk_id` ordering scrambles pages with 10+ chunks

**File:** `doc_store.py:283`
**Category:** Correctness (ordering)
**Issue:** `ORDER BY page ASC, chunk_id ASC` sorts `..._p1_10` before `..._p1_2`.
Any rebuild-from-store path (CR-01) restores chunks out of order, corrupting context
assembly. Same hazard applies to any `sorted()` on chunk IDs elsewhere.
**Fix:** Zero-pad the chunk sequence (`f"{sha12}_p{page_num}_{j:04d}"`) or order by
`char_start`/`rowid`.

### WR-07: Disk cache is write-only — `.cache/` dumps never read back

**File:** `main.py:190-201`
**Category:** Quality (dead store)
**Issue:** `pages.json`/`chunks.json`/`manifest.json` are written best-effort on every
upload but no code path reads them (STORE-03 "cache layout" is half-delivered). Stale
caches accumulate with no invalidation beyond `CONFIG_VERSION`, and `.cache/` is not
in `.gitignore` (only `data/` is) — cache artifacts will be accidentally committed.
**Fix:** Either implement the read path (skip re-extraction when manifest matches
`CONFIG_VERSION`) or downgrade to clearly-marked debug dumps; add `.cache/` to
`.gitignore` regardless.

### WR-08: Inconsistent timestamp formats break ordering and display

**File:** `main.py:142-144, 177, 208` + `doc_store.py:191`
**Category:** Correctness
**Issue:** Three formats coexist: ISO with `+00:00` (persisted `Document.upload_time`),
`%H:%M:%S` time-only (session metadata, line 208 — drops the date entirely), and
`Z`-suffixed strings in tests. `list_documents ORDER BY upload_time DESC` compares these
lexicographically, where `'Z' (0x5A) > '+' (0x2B)` regardless of actual time — mixed
rows sort wrong. Time-only display strings are ambiguous across days.
**Fix:** Store and display one canonical form (`datetime.now(timezone.utc).isoformat()`
everywhere); format for display only at render time.

## Info

### IN-01: `sha256_bytes(...).lower()` is a no-op

**File:** `upload_validation.py:32`
`hashlib.sha256().hexdigest()` already returns lowercase. Harmless; remove to avoid
implying uppercase input is possible.

### IN-02: `BBox` accepts inverted/negative coordinates

**File:** `models.py:29-41`
No validator enforces `x1 > x0`, `y1 > y0`, or non-negativity. Dormant today (no bbox
producer exists yet) — add a `model_validator` when Phase 3/4 starts producing boxes.

### IN-03: Filenames interpolated into Markdown UI — markup injection

**File:** `main.py:125, 153, 168, 171, 194, 201, 212`
`st.write(f"Validating `{filename}`…")` etc. render attacker-controlled filenames as
Markdown (links/images via `[x](url)` outside backticks in some paths, e.g. line 212's
`st.success(f"**{filename}** ...")`). Backticks mitigate most, but `st.success` wraps in
bold markers, not code spans. Prefer `st.code`/escaped rendering for raw filenames.

### IN-04: `cache_dir_for` permits path traversal on untrusted input

**File:** `models.py:15-26`
`base / sha256 / CONFIG_VERSION` with an unsanitized `sha256` argument allows
`cache_dir_for(base, "../../etc")` escapes. Current caller passes an internally
computed hash (safe), but the helper is public and unguarded. Add a
`^[0-9a-f]{64}$` assertion.

### IN-05: Oversize test allocates ~51 MB; over-page test relies on global monkeypatch

**File:** `tests/test_upload_validation.py:54-58, 61-76`
The oversize vector is built in-memory on every run; the page-cap test monkeypatches
`pypdf.PdfReader` globally (reverted by the fixture, but order-dependent if tests ever
run in parallel with `pytest-xdist`). Consider patching `MAX_FILE_MB` small and
patching the `pypdf` reference inside `upload_validation` instead.

### IN-06: `record_chunks` upsert refreshes only 3 of 9 columns on conflict

**File:** `doc_store.py:240-247`
`ON CONFLICT(chunk_id) DO UPDATE` refreshes `content/bbox_json/embedding_model` but
leaves stale `doc_id/filename/page/char_start/char_end/extraction`. Harmless while
chunk IDs are content-derived, but a re-chunk under a new config version silently keeps
old page/offsets. Include the positional columns in the update set.

## Per-File Notes

- **models.py** — Clean Pydantic v2 usage, correct `frozen`/`extra="forbid"` placement,
  good docstrings. Gaps are all omission-side: no cross-field validators (WR-05), no
  BBox geometry checks (IN-02), unsanitized `cache_dir_for` (IN-04).
- **doc_store.py** — Solid DDL, parameterized queries throughout (no SQL injection),
  correct upsert shapes, good type guards. Must-fix lifecycle bug: connections never
  closed (WR-01). Minor: timestamp sort fragility (WR-08), partial chunk refresh (IN-06).
- **upload_validation.py** — Correct fail-fast order, accurate error fragments, honest
  streaming-hash implementation. Ordering flaw is architectural (caller buffers first,
  WR-04); magic-byte check is strict-prefix (rejects leading-BOM PDFs — acceptable,
  fail-closed). Polyglot-with-valid-header falls through to the pypdf probe, which
  rejects rather than crashes — adequate for v1.
- **pdf_reader.py** — Fault isolation works for `extract_text()` failures but the guard
  is scoped too narrowly (WR-02); chunk-ID migration preserves legacy default path
  correctly; `Path().name` filename handling is Windows-safe. Compat with
  `LocalEmbedding.build_index` dict passthrough and `VectorIndex` content-key guard
  verified — `model_dump()` superset is safe.
- **main.py** — Staged UI wiring follows existing `st.status`/`st.progress` idioms well.
  Contains all three Criticals (CR-01/02/03): dedup-without-restore, unguarded
  constructor, missing `record_chunks` call. `import io` hoisting was done per plan.
- **tests/** — Strong contract coverage (legacy-key exactness, frozen/hash, tracer
  round-trip, interleave, rename-stability). Brittle spots: 51 MB allocation (IN-05),
  `test_sha_unique_violation_on_reupload` pins a raise no production caller handles
  (WR-03), and no test covers the dedup-hit-with-empty-index path (the CR-01 gap —
  add one with a pre-populated `DocStore` + empty session index).
- **requirements.txt** — `pydantic==2.11.9` pin present and exact. `numpy>=1.26.0,<3.0.0`
  range is loose relative to the otherwise fully pinned file — out of phase scope, noted only.
- **local_embedding.py / vector_index.py / conftest.py** (compat spot-check) — No changes
  needed for compat; `build_index` accepts the `model_dump()` superset (extra keys pass
  through as stored metadata), ` VectorIndex` content-key requirement satisfied. No
  findings in these files.

## Fix Priority

1. **CR-01 + CR-03 together** — persist chunks on upload and rebuild the session index
   on dedup-hit; this is one coherent fix restoring the restart story. Add a regression
   test: pre-populated `DocStore` (via `record_chunks`) + empty session index →
   dedup-hit path yields a queryable index.
2. **CR-02** — wrap `PdfReader` construction + extraction in per-file try/except with
   `st.error + continue`.
3. **WR-01** — close SQLite connections (`contextlib.closing`).
4. **WR-02** — extend page guard over split + `Chunk` construction (or pre-filter
   whitespace-only splits).
5. **WR-03** — handle `IntegrityError` at the `upsert_document` call site.
6. **WR-04 / WR-07 / WR-08** — size pre-check via `UploadedFile.size`; define cache
   read-or-remove policy + `.gitignore` the `.cache/` dir; unify timestamps to UTC ISO.
7. **WR-05 / WR-06 + Info items** — validators for doc_id↔sha and status literals;
   zero-padded chunk sequences; remaining hardening.

---

_Reviewed: 2026-10-11T02:30:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
