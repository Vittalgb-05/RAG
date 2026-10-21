---
status: resolved
trigger: |
  Root-cause assessment: PDF question extraction and answer grounding

  The screenshots show two separate failures in your local PDF assistant:

  1. The model does not answer the actual question. When asked "what are the questions?",
     it repeats "What are the primary findings?" twice instead of extracting the questions
     from EVS.pdf.
  2. The evidence panel and answer disagree. The interface displays eight retrieved evidence
     snippets, but the response contains no [E#] citations and is explicitly marked
     "Ungrounded response."

  User instruction: make changes based on all the codebase map docs in .planning/codebase/
  Reproduce, find root cause, fix, and add an EVS question-extraction regression test.
created: 2026-10-21
updated: 2026-10-21
slug: evs-questions-grounding
---

# Debug Session: EVS Question Extraction and Grounding Enforcement

**Session Slug:** `evs-questions-grounding`

## Symptoms

**Expected behavior:**
- Query `"What are the questions?"` on the selected `EVS.pdf` extracts the actual questions from the document in page order, including subparts and marks where present.
- The answer cites the evidence it uses with `[E#]` tokens, and the evidence panel/chips reflect only evidence cited by the accepted answer.
- A response that fails grounding is blocked, retried with focused evidence, or clearly rejected — it is not rendered as a normal answer.

**Actual behavior:**
- The model repeats "What are the primary findings?" twice instead of extracting the exam questions.
- Eight evidence snippets are shown (pages 1, 2, 3, 9), but the answer contains no `[E#]` citations and is labelled "Ungrounded response."
- Citation chips for retrieved evidence imply grounding even though the displayed answer cites nothing.

**Errors / UI:**
- Grounding caption: "Ungrounded response."
- No numeric citation precision displayed in the screenshot.
- Evidence drawer lists eight snippets that are not reflected in the answer.

**Timeline:**
- Reported 2026-10-21. Unknown whether this exact query ever worked; a prior resolved session (`rag-answer-quality-and-citations`) fixed chunk fragmentation and query contextualization, so this may be a regression or an unhandled extraction-intent path.

**Reproduction:**
- Select `EVS.pdf` (11-page exam booklet) in Chat.
- Ask exactly: `What are the questions?`
- Observe answer, citation chips, evidence drawer, and grounding caption.
- `EVS.pdf` is not present in the repo; reproduce structurally with a synthetic multi-page question document and the existing corpus, and add a regression test that does not require the real file.

## Current Focus

hypothesis: Whole-document extraction is routed through generic top-k chat RAG (k=8) and the grounding result is advisory in the UI, so the model never sees the complete question inventory and an uncited answer is still rendered with retrieved-evidence chips.
test: Trace the chat path in `ui/views.py` -> `AiModel` -> `HybridRetriever.search_hybrid` -> `CitationValidator`; assert which query string, doc scope, k, prompt and validation result reach each stage. Then reproduce with a synthetic 3+ page question PDF and the exact query.
expecting: Either (a) the query is rewritten or retrieval is globally scoped, so question text on later pages never reaches the prompt, and/or (b) validation returns ungrounded but the view renders the answer and all candidate chips anyway.
next_action: none — resolved and verified (see Resolution)
reasoning_checkpoint: CONFIRMED. (a) fixed `k=8` retrieval omitted pages 5, 10, 11 of an 11-page synthetic booklet; (b) the system prompt few-shot example contained the literal phrase "What are the primary findings?", which the 2B model echoed; (c) `ui/views.py` had `if (not cited_ranks or rank in cited_ranks)`, so zero citations rendered every candidate chip, and the uncited draft was streamed as a normal answer.

## Evidence

- timestamp: 2026-10-21 — codebase map (`./.planning/codebase/ARCHITECTURE.md`, `CONCERNS.md`) reports fixed top-k chat retrieval and duplicated follow-up rewriting; summarizer/retrieval evidence handling also flagged.
- timestamp: 2026-10-21 — real `EVS.pdf` unavailable in repo; regression must use a synthetic multi-page question document.
- timestamp: 2026-10-22 — Reproduced structurally with an 11-page synthetic question booklet + deterministic 384-dim hashing embeddings (no GPU): `search_hybrid("What are the questions?", k=8, doc_id="doc_evs")` returned 8 snippets covering pages 1,2,3,4,6,7,8,9 and silently omitted pages 5,10,11. Assembled prompt confirmed the missing pages.
- timestamp: 2026-10-22 — Reproduced prompt contamination: `SYSTEM_GROUNDING_TEMPLATE` contained `Question: What are the primary findings?` — the exact phrase the model echoed in the report. A 2B model copying the few-shot example explains the repetition.
- timestamp: 2026-10-22 — Reproduced UI advisory grounding: live path used `if (not cited_ranks or s.get("rank") in cited_ranks)` so an answer with zero citations still rendered all 8 candidate chips; the ungrounded draft was already streamed by `st.write_stream` before validation.
- timestamp: 2026-10-22 — Confirmed duplicated follow-up heuristic in `ui/views.py` and `core/local_llm.py` (CONCERNS.md), with the UI path always supplying `retrieval_result`, making the AiModel copy dead and divergent.

## Eliminated

- Hypothesis: the embedding model itself is broken. Ruled out — the failure is structural (k cap and prompt contamination), reproduced with a deterministic embedding that ranks every question page highly.
- Hypothesis: document scope was lost. Ruled out — `doc_filter` is pushed into dense/FTS search; the omission came from the final `[:k]` truncation, not cross-document crowding.
- Hypothesis: citation regex fails on valid output. Ruled out — `validate_citations` correctly returns `total_citations == 0` for the reported draft; the defect was that the view did not enforce that result.

## Resolution

**Root cause:**
Three interacting defects: (1) whole-document/inventory questions ("What are the questions?") were answered from a fixed `k=8` similarity-ranked sample, so later question pages never reached the model; (2) the grounding system prompt's few-shot example literally contained "What are the primary findings?", which the small local model echoed instead of answering; (3) grounding was advisory in the UI — an uncited draft was streamed as a normal answer and, because `cited_ranks` was empty, all retrieved candidates were rendered as citation chips.

**Fix:**
- Added `core/query_intent.py`: one shared follow-up contextualizer (removes duplicated heuristics), inventory-intent detection, page-diverse evidence selection under the 4K context budget, and `resolve_retrieval()` which switches to whole-document, page-ordered retrieval for inventory questions.
- Added `HybridRetriever.fetch_document_chunks(doc_id)` returning every indexed chunk in page order with contiguous ranks (works on LanceDB and the fallback mirror).
- Wired the whole-document path into `ui/views.py` and `AiModel` (new optional `doc_id`), including the unambiguous single-document "All Documents" case.
- Rewrote the grounding few-shot example (no user-query phrase), added an explicit enumerate-in-document-order rule, and removed the seeded "primary findings" wording.
- Enforced grounding at render time via `should_withhold_answer()`: ungrounded, invalid-citation, and injection-echo drafts are streamed into a placeholder, then replaced with a rejection notice plus a collapsed rejected draft. Rejected content is not re-injected into model history.
- Citation chips now render only cited ranks; uncited candidates are clearly labelled "Retrieved Candidate Context (Uncited)" in both live and replayed turns.

**Verification:**
- New `tests/test_whole_document_extraction.py` (8 tests): intent detection, shared follow-up heuristic, page-ordered fetch, all `>k` pages covered, budget-constrained page coverage with contiguous ranks, prompt decontamination, end-to-end AiModel prompt contains all 11 question pages, and the grounding gate (abstention allowed, cited allowed, hallucinated/uncited withheld).
- Full suite: `python -m pytest -q` → **326 passed**.
- `python -m ruff check .` → clean; `python -m ruff format --check .` → clean.
- Note: live GPU/llama-server output was not exercised (no model/GPU in this environment); verification is structural and deterministic.

**Files changed:**
- `core/query_intent.py` (new)
- `retrieval/hybrid_retriever.py`
- `core/local_llm.py`
- `core/prompt_budget.py`
- `core/citation_validator.py`
- `core/models.py`
- `ui/views.py`
- `tests/test_whole_document_extraction.py` (new)
- `.planning/debug/evs-questions-grounding.md` (session record)
