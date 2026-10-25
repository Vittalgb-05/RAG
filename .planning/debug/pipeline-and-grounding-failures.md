# Debug Session: Pipeline & Grounding Failures
**Status:** RESOLVED  
**Created:** 2026-10-25  
**Resolved:** 2026-10-26  
**Slug:** pipeline-and-grounding-failures

---

## Symptoms

| Field | Detail |
|-------|--------|
| **Expected** | "List all questions in this PDF" → exhaustive, ordered list with page citations |
| **Actual** | Model returns partial list, repeats the user's question as the answer, or abstains even though evidence is present |
| **Related** | Citation-validity shown as 100% while answer is generic / answer says "no evidence" while chips show candidates |
| **Timeline** | Present since original architecture; confirmed in screenshots |
| **Reproduction** | Upload a question-paper PDF → ask "mention all the questions that are there in the question paper" |

---

## ROOT CAUSE FOUND

Five root causes confirmed from codebase inspection. Ranked P0 → P1.

---

### [P0-A] `is_whole_document_query` pattern gap — "mention all the questions" falls through to top-k

**File:** [`core/query_intent.py`](file:///c:/Users/OM%20Prakash/Documents/RAG/core/query_intent.py#L38-L54)

**Evidence from source:**
```python
_WHOLE_DOCUMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b(?:what|which)\s+(?:are|were)..."),   # ✓ "what are the questions"
    re.compile(rf"\bwhat\s+{_INVENTORY_NOUNS}..."),        # ✓ "what questions does..."
    re.compile(rf"\b(?:list|extract|enumerate|...)..."),   # ✓ "list all questions"
    re.compile(rf"\ball\s+(?:of\s+)?(?:the\s+)?..."),      # ✓ "all the questions"
    re.compile(r"\b(?:every|each)\s+..."),                 # ✓ "every question"
    re.compile(r"\b(?:whole|entire|full)\s+..."),          # ✓ "whole document"
    re.compile(r"\bsummar..."),                            # ✓ "summarize the whole..."
)
```

**Gap confirmed:** The phrase **"mention all the questions that are there in the question paper"** contains `mention` + `all` + `questions`, but none of the patterns match because:
- Pattern 3 anchors on `\b(?:list|extract|enumerate|identify|name|provide|give|show)\b` — `mention` is not in that verb list.
- Pattern 4 anchors on `\ball\s+(?:of\s+)?(?:the\s+)?{_INVENTORY_NOUNS}\b` — the phrase "all the questions that are there" does NOT match because `all the questions` is followed by ` that are there`, but the pattern requires the inventory noun to end the match. Actually, `\ball\s+(?:of\s+)?(?:the\s+)?{_INVENTORY_NOUNS}\b` uses `\b` at the end of the noun, so "all the questions that are there" WOULD match because `\b` fires after `questions`. **Re-checking…**

> **Re-evaluation:** `\ball\s+(?:of\s+)?(?:the\s+)?{_INVENTORY_NOUNS}\b` should match "all the questions" inside "all the questions that are there". The `\b` after the noun group fires at the end of `questions`. So pattern 4 DOES capture it.

> **Deeper check needed:** The `resolve_retrieval` function at line 222 requires `isinstance(doc_id, str) and doc_id`. If the user has not explicitly set a document filter AND there is more than one document, `retrieval_scope` may be `None` (views.py:703-705 only auto-sets it when there is exactly one doc). A `None` doc_id causes `resolve_retrieval` to skip the whole-document branch entirely and fall back to top-k search.

**Confirmed bug:** With >1 document in the library, or if auto-detect (`retrieval_scope`) leaves `doc_id=None`, the whole-document path is NEVER taken — even when the query clearly matches. The view at line 704 only auto-fills `retrieval_scope` when `len(document_metadata) == 1`.

**Fix:** If `is_whole_document_query()` returns True and `doc_id` is still None, prompt the user to select a document OR apply exhaustive extraction to all indexed documents sequentially (or refuse gracefully with an explanation).

Also add `mention` + common Hindi-English phrasing to the verb list in pattern 3.

---

### [P0-B] Token budget arithmetic can exceed the 4096-token context window

**Files:** 
- [`core/prompt_budget.py:74`](file:///c:/Users/OM%20Prakash/Documents/RAG/core/prompt_budget.py#L74) — `max_output_tokens=1536` default
- [`core/local_llm.py:339`](file:///c:/Users/OM%20Prakash/Documents/RAG/core/local_llm.py#L339) — asks provider for `max_tokens=2048`
- [`core/query_intent.py:109`](file:///c:/Users/OM%20Prakash/Documents/RAG/core/query_intent.py#L109) — char budget assumes `max_output_tokens=1024`

**Confirmed from source:**
- `assemble_grounded_messages` reserves 1536 output tokens in the input budget.
- `stream_text` is then called with `max_tokens=2048`.
- The char budget for whole-document uses 1024 output tokens.
- Three different numbers for the same thing → context window is over-committed.

With a 4096-token window: `system_prompt (~400) + context + history + user_prompt + 2048 output` can exceed 4096. llama.cpp will silently truncate or reject the tail of the prompt.

**Fix:** Define a single `MAX_OUTPUT_TOKENS = 1536` constant in `core/prompt_budget.py`, pass it to `assemble_grounded_messages`, `whole_document_char_budget`, and every `stream_text`/`generate_text` call. Assert `estimated_input + max_output ≤ context_window` in a test.

---

### [P0-C] Citation validity ≠ answer completeness — misleading "100% valid" label

**File:** [`core/citation_validator.py:383-390`](file:///c:/Users/OM%20Prakash/Documents/RAG/core/citation_validator.py#L383-L390)

**Confirmed from source:**
```python
valid_ranks = [r for r in ranks if 1 <= r <= max_valid_rank]
precision = len(valid_ranks) / total_claimed
is_valid = precision >= 0.95
```
`is_valid=True` simply means every `[E#]` tag points at a real retrieved chunk — it says **nothing** about whether the answer is complete, correct, or supported. The `support_precision` field exists and is computed, but is only a diagnostic warning; it never changes `is_valid`.

**Auto-attribution amplifies the problem:** `auto_attribute_citations` (lines 418-506) appends `[E#]` to uncited sentences at `min_overlap=0.18` (18%), and those auto-added citations then pass the `is_valid` check. The UI then renders "Citation validity 100%" for a generated answer that the model never cited.

**Fix:**
1. Separate `citation_exists` (current `is_valid`) from `evidence_supports_claim` (use `support_precision` threshold, e.g. ≥ 0.35).
2. Add a `completeness_check` flag: did the answer actually address the question?
3. Mark auto-attributed citations distinctly — they must not count toward the stated precision target.
4. Never display "100% valid" if `support_precision < 0.35` or `auto_attributed_count > 0`.

---

### [P1-A] Whole-document retrieval silently capped at 500 chunks

**File:** [`retrieval/hybrid_retriever.py:641`](file:///c:/Users/OM%20Prakash/Documents/RAG/retrieval/hybrid_retriever.py#L641)

```python
def fetch_document_chunks(self, doc_id: str, limit: int = 500) -> RetrievalResult:
```

An 11-page question paper with normal chunking produces ~30 rows (per the log: "opened existing `chunks` table with 30 rows"). For this specific document the limit is irrelevant. However, for any >500-chunk document, later pages are silently dropped with no warning surfaced to the user or the `RetrievalResult`. CONCERNS.md §Known Bugs confirms this.

**Fix:** Add `omitted_chunks: int` field to `RetrievalResult`; set it when `len(fetched) >= limit`; surface a warning in the chat view. For the immediate EVS.pdf case (30 chunks), this is NOT the failing cause — but must be fixed for robustness.

---

### [P1-B] `retrieval_scope` auto-detection skips single-document check when doc filter is explicit but wrong

**File:** [`ui/views.py:700-714`](file:///c:/Users/OM%20Prakash/Documents/RAG/ui/views.py#L700-L714)

The `retrieval_scope` / `doc_filter` is passed to `resolve_retrieval` which passes it to `fetch_document_chunks`. If `doc_filter` is set to a specific doc but the query-intent match fails (P0-A scenario), the call becomes a regular top-k search against only that document's chunks. This is correct behavior when intent detection is working but becomes the bottleneck when intent detection misses phrases.

---

## Evidence Map

| Symptom | Root Cause | File / Line |
|---------|-----------|-------------|
| "mention all questions" → top-k instead of exhaustive | P0-A: doc_id=None or verb gap | `query_intent.py:222`, `views.py:703-705` |
| Model repeats user question | P0-B: context truncated, model falls back on prompt | `prompt_budget.py:74` vs `local_llm.py:339` |
| 100% citation valid but answer generic | P0-C: auto-attribution + existence-only check | `citation_validator.py:383-418` |
| "Context truncated; some evidence omitted" log | P0-B: budget mismatch | `prompt_budget.py:97` |
| Evidence chips shown but answer says "no evidence" | P0-C: abstention marker match beats actual content | `citation_validator.py:102-116` |

---

## Fix Plan (Ordered)

### Fix 1 — Intent routing when doc_id is None (P0-A) 
**Files:** `core/query_intent.py`, `ui/views.py`

- In `resolve_retrieval`: if `is_whole_document_query(query)` is True but `doc_id` is not a string, return an `RetrievalResult` with a `search_mode="intent_mismatch"` so the UI can warn the user to select a specific document.
- In `ui/views.py` chat handler: if `search_mode == "intent_mismatch"`, show `st.warning("Please select a specific document to extract all questions from it.")` and skip generation.
- Extend `_WHOLE_DOCUMENT_PATTERNS` to include `mention` in the verb group and add patterns for "what questions are in this", "what are the questions in the paper", "questions in the document".

### Fix 2 — Unified output token budget (P0-B)
**File:** `core/prompt_budget.py`, `core/local_llm.py`, `core/query_intent.py`

- Add constant `DEFAULT_MAX_OUTPUT_TOKENS = 1536` to `core/prompt_budget.py`.
- Pass it as default to `assemble_grounded_messages` and to `whole_document_char_budget`.
- Change `stream_text` call in `local_llm.py:339` to use same constant.
- Add assertion: `assert base_system_tokens + context_tokens + history_tokens + prompt_tokens + DEFAULT_MAX_OUTPUT_TOKENS <= caps.context_window` with a logged warning (not a hard error).

### Fix 3 — Citation quality gates (P0-C)
**Files:** `core/citation_validator.py`, `ui/views.py`

- Add `auto_attributed_count: int` field to `CitationVerificationResult`.
- Track how many citations were appended by `auto_attribute_citations` vs model-generated.
- In `verification_caption()` in views.py: display separate labels — "Grounded" (model cited), "Auto-attributed" (lexical match), "Unsupported" (lexical miss).
- Never label a response "Citation validity 100%" when `auto_attributed_count > 0`; use "Auto-attributed citations" instead.
- Add `SUPPORT_TOKEN_THRESHOLD`-gated warning: if `support_precision < 0.35`, label as "Partially supported".

### Fix 4 — Fetch chunk cap warning (P1-A)
**File:** `retrieval/hybrid_retriever.py`, `core/models.py`

- Add `total_fetched: int` and `chunk_cap_reached: bool` to `RetrievalResult` (or via `search_mode="document_truncated"`).
- Set flag when `len(rows) >= limit` in `fetch_document_chunks`.
- Surface in UI as `st.caption("⚠️ Document too large to fully index in one pass — {n} chunks retrieved.")`.

---

## Test Cases (Acceptance Criteria)

| # | Input | Expected Result | Validates |
|---|-------|-----------------|-----------|
| 1 | EVS.pdf + "mention all the questions" + single doc | Exhaustive list, all pages covered | Fix 1 |
| 2 | EVS.pdf + "What are the questions?" + multi-doc library (no filter) | Warning: "Select a specific document" | Fix 1 |
| 3 | Maximum-evidence prompt (8 chunks × ~300 chars) | No context truncation, `max_tokens` consistent | Fix 2 |
| 4 | Model omits citations → auto-attribution runs | Caption says "Auto-attributed" not "100% valid" | Fix 3 |
| 5 | Model cites [E1] but sentence unrelated to snippet | `support_precision < 0.35` → "Partially supported" | Fix 3 |
| 6 | Document with 600 chunks | Warning: chunk cap reached, tail pages missing | Fix 4 |
| 7 | "What is acid rain?" → narrow answer | Top-k path used, NOT whole-document | Fix 1 regression |
| 8 | Abstract fact with citation | `citation_exists=True`, `evidence_supports_claim=True`, "Grounded" label | Fix 3 |

---

## Files to Change

| File | Change |
|------|--------|
| `core/query_intent.py` | Extend verb list; add `intent_mismatch` path when `doc_id` is None |
| `core/prompt_budget.py` | Add `DEFAULT_MAX_OUTPUT_TOKENS = 1536`; use in `assemble_grounded_messages` |
| `core/local_llm.py` | Use `DEFAULT_MAX_OUTPUT_TOKENS` in `stream_text` call |
| `core/citation_validator.py` | Add `auto_attributed_count`; separate `citation_exists` from `support_score` |
| `core/models.py` | Add `chunk_cap_reached: bool = False` to `RetrievalResult` |
| `retrieval/hybrid_retriever.py` | Set `chunk_cap_reached` when `len(fetched) >= limit` |
| `ui/views.py` | Handle `intent_mismatch`; update `verification_caption`; show chunk-cap warning |
| `tests/test_query_intent.py` | Add tests for new verb patterns and doc_id=None path |
| `tests/test_citation_validator.py` | Add auto-attribution tracking tests |
| `tests/test_prompt_budget.py` | Add token-budget invariant test |

---

## Do NOT Do

- Do NOT replace Qwen2-VL 2B before testing with a manually prepared prompt (the model may be fine; the pipeline is the issue).
- Do NOT add a second query-rewriting pass — `contextualize_query` is already the single shared path.
- Do NOT rewrite the whole architecture — existing components (`resolve_retrieval`, `fetch_document_chunks`, `select_page_diverse_snippets`) are correct once `doc_id` routing is fixed.

---

*Debug session created: 2026-10-25*
*Debug session resolved: 2026-10-26*

---

## Resolution Summary

1. **[P0-A] Whole-Document Intent & Routing Gap:**
   - Extended `_WHOLE_DOCUMENT_PATTERNS` in `core/query_intent.py` with `_EXTRACTION_VERBS` including `mention`, `tell`, `state`, `display`, `print`, and phrasing like "mention all the questions that are there in the question paper".
   - In `resolve_retrieval`: when exhaustive inventory query intent is detected but `doc_id` is None (or a multi-doc list), return `RetrievalResult(..., search_mode="intent_mismatch")`.
   - In `ui/views.py`: render user warning prompting document selection for exhaustive queries rather than falling back to incomplete top-k answer.
2. **[P0-B] Unified Output Token Budget & Invariant:**
   - Established single source of truth `DEFAULT_MAX_OUTPUT_TOKENS = 1536` across `core/prompt_budget.py`, `core/local_llm.py`, and `core/query_intent.py`.
   - Fixed prompt/context truncation to account for truncation notice tokens, strictly respecting `total_input_budget` + `DEFAULT_MAX_OUTPUT_TOKENS <= context_window`.
3. **[P0-C] Citation Quality Gates & Auto-Attribution Transparency:**
   - Added `auto_attributed_count` tracking to `CitationVerificationResult` and `ui/views.py`.
   - Updated `verification_caption` with three honest support tiers (grounded, partially supported, weakly supported) and transparent labels when citations are auto-attributed vs model-generated.
4. **[P1-A] Chunk Cap Warning:**
   - Added `chunk_cap_reached` to `RetrievalResult` and surfaced warning in UI when `len(rows) >= limit`.

### Test Verification
- All 399 tests across the entire test suite pass (`399 passed in 38.49s`).
- Linter checks pass (`ruff check .` with 0 warnings/errors).
- Code formatting verified (`ruff format --check .` with 77 files clean).
- Synthetic test corpus generation verified (`python tests/data/corpus/generate_corpus.py`).

