---
status: resolved
trigger: |
  IMPLEMENTATION TASK: Repair PDF Grounding and Rebuild the Streamlit UI

  Repository: C:\Users\OM Prakash\Documents\RAG (local-first PDF intelligence app:
  Streamlit, local llama-server, Qwen2-VL 2B, Docling, RapidOCR, Sentence Transformers, LanceDB).

  Deliverable 1: Eliminate unsupported summaries and incorrect document attribution.
  Deliverable 2: Replace the cluttered Streamlit interface with the supplied minimalist
  dark chatbot design.

  Observed failure: user selected Omprakash_Panda_Resume.pdf (only document) and asked
  "Summarize the core thesis and key findings of the document in detail." The app produced:
  - "Environmental studies is multidisciplinary."
  - "Sustainable development balances ecological conservation with socioeconomic growth."
  - "Benchmarks show a 2x speedup."
  - "An algorithm has O(n log n) time complexity and O(n) space complexity."
  The displayed source was the resume, whose visible content describes professional
  experience, a GraphRAG pipeline, incident retrieval, software engineering and education.
  It does not substantiate the environmental-studies or benchmark claims.
  Follow-up questions ("whose resume is this?", "who is Omprakash?") were answered
  consistently with the resume evidence.

  Required behavior: summaries must reflect actual selected-document evidence; no invented
  environmental/benchmark/complexity claims; insufficient extraction must be reported;
  every displayed source must belong to the selected scope and support its claim; unrelated
  questions must abstain rather than silently search other documents.

  User instruction: inspect the real repository, identify the implementation responsible for
  each defect, make the smallest coherent set of changes, run all automated checks
  (pytest, ruff check, ruff format --check), and report the confirmed root cause, changed
  files, request-flow changes, test results, and remaining manual verification. Do not stop
  at a plan, do not mock working services, do not delete data/index/model/PDF/cache.
created: 2026-10-29
updated: 2026-10-29
slug: pdf-grounding-and-streamlit-ui
---

# Debug Session: PDF Grounding + Streamlit UI Redesign

## Symptoms

**Expected behavior**
- A resume selected as the only document summarizes its actual content (experience,
  projects, skills, achievements, education) with page-grounded citations.
- No environmental-science, benchmark-speedup, or complexity claims unless present in the
  selected document.
- Insufficient extraction yields an explicit parsing/evidence limitation, not a generic summary.
- Every displayed source belongs to the selected document and supports its adjacent claim.
- "Who is Omprakash?" uses only resume-supported facts.
- A question unrelated to the selected document abstains; no silent all-document search.
- Citation existence and claim support are validated separately.
- Switching documents cannot leak the previous document's evidence.
- UI matches the reference: centered dark chat, minimal composer, restrained accents,
  no duplicated navigation, zero emojis, real provider health, real backend events.

**Actual behavior**
- Summary path generated unrelated claims (environmental studies, 2x speedup, O(n log n),
  O(n) space) while displaying the resume as source.
- Later Q&A ("whose resume is this?", "who is Omprakash?") appeared grounded in resume evidence,
  so the divergence is specific to the summary request path.
- Current UI is cluttered with competing navigation elements.

**Errors**
- No explicit exception reported; failure is silent ungrounded generation / misattribution.

**Timeline**
- Reported 2026-10-29 against current branch. Unknown whether this exact summary path ever
  worked; prior resolved sessions (pipeline-and-grounding-failures, evs-questions-grounding,
  rag-answer-quality-and-citations) touched retrieval and grounding, so this may be a
  regression or an unhandled summary-specific path.

**Reproduction**
- Select Omprakash_Panda_Resume.pdf as the only document.
- Ask: "Summarize the core thesis and key findings of the document in detail."
- Observe answer text, citations, displayed sources, and grounding label.
- Then ask "whose resume is this?" and "who is Omprakash?" to compare the QA path.
- Resume PDF is not assumed present in the repo; reproduce structurally with synthetic
  fixtures and deterministic mocks that do not require the local LLM.

## Current Focus

hypothesis: CONFIRMED. `SYSTEM_GROUNDING_TEMPLATE` shipped the exact fabricated claims as
few-shot worked examples; one shared token was enough to auto-attach a real resume citation;
validation checked only citation-rank existence; and the renderer labelled any rank-valid
answer "Grounded" while falling back to unrelated snippets as sources. Fixes applied and
regression-tested.
test: `python -m pytest -q` (453 passed), `python -m ruff check .`, `python -m ruff format --check .`.
next_action: none (resolved; manual browser verification outstanding, listed in Resolution)

## Required Technical References (Part 7)

The user added these mandatory references and application rules. Read them, then translate
their relevant principles into concrete changes; do not merely cite them in the report.

**A. RAG grounding / citation correctness**
- Correctness is not Faithfulness in RAG Attributions — https://arxiv.org/abs/2412.18004
  Apply to `core/citation_validator.py`, `core/prompt_budget.py`, `ui/chat_controller.py`,
  the summarization service and tests. Separate citation existence, relevance and factual
  support; never mark grounded merely because an `[E#]` ID exists; check claims against the
  actual cited text; prevent unsupported claims from being shown as verified; add a regression
  where a valid citation points to the resume while the claim discusses environmental science.
- Evaluation of RAG: A Survey — https://arxiv.org/abs/2405.07437
  Apply to `retrieval/hybrid_retriever.py`, `retrieval/local_embedding.py`,
  `ui/chat_controller.py`, the summarizer and retrieval/generation tests. Test retrieval
  relevance separately from answer faithfulness; verify relevant chunks reach the prompt;
  verify the answer uses supplied evidence; evaluate citation support separately from retrieval
  success; preserve document/page provenance. Do not respond by only increasing `k`, swapping
  embeddings or adding prompt instructions — first locate the failing stage.
- CiteGuard-RAG — https://arxiv.org/abs/2609.15830
  Architectural reference: generate candidate, validate claims against supplied evidence,
  accept OR at most one bounded regeneration OR abstain; record rejection reason; no unbounded
  retry loops.

**B. Streamlit UI**
- Chat elements — https://docs.streamlit.io/develop/api-reference/chat
- Build a basic LLM chat app — https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps
- Chat message — https://docs.streamlit.io/develop/api-reference/chat/st.chat_message
  Use supported chat components and `st.chat_input`; do not nest `st.chat_message`; keep
  history in the existing session/persistence architecture; use supported status components;
  centralize scoped styling in `ui/theme.py`; check the installed Streamlit version; test actual
  UI behavior. The visual target remains the supplied minimalist black chatbot design.

**C. Local multimodal inference**
- llama.cpp multimodal — https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md
  Preserve the existing `llama-server` integration; verify model/projector compatibility; keep
  provider config separate from UI; do not start a second server or adapter; preserve explicit
  local/cloud selection and truthful network-usage status. Do not change model/quantization/
  GPU-offload unless investigation proves it necessary.

**D. Repository-specific proof requirements**
- Unrelated summary claims: reproduce the resume test and identify where unsupported content
  enters the pipeline.
- Incorrect attribution: show how document ID, evidence ID, page and text are preserved or
  mismatched.
- Missing chunks: compare retrieval results with context actually sent to generation.
- Unsupported citations: demonstrate a valid ID with irrelevant evidence fails support checks.
- Stale state: test document switching and summary cache invalidation.
- Broken UI navigation/controls: exercise each workspace and trace upload, delete, summarize,
  chat, citation and provider actions to real handlers.
Research references establish plausibility only; repository inspection and reproducible results
establish the local cause.

**E. Completion rules**
Inspect the codebase map and current git diff before editing; make the smallest coherent change
set; preserve working features and user changes; never delete data/models/indexes/caches; add a
regression test per confirmed bug; run full pytest + Ruff lint/format; report actual CI status
(do not claim remote CI passed unless observed); report manual browser checks still needed;
separate deterministic mock coverage from live-model behavior. Final report must include the
confirmed root cause, supporting evidence, files changed, tests run, UI behavior implemented and
unresolved limitations.

## Evidence

- timestamp: 2026-10-29T00:00:00Z | `git log -1 1bb5121` (HEAD) adds "multi-passage synthesis instruction and worked example to system template".
- timestamp: 2026-10-29T00:00:01Z | `core/prompt_budget.py:38-44` `SYSTEM_GROUNDING_TEMPLATE` literally contains the observed hallucinations as few-shot answers: "Environmental studies is multidisciplinary", "Sustainable development balances ecological protection and economic growth", "O(n log n) time / O(n) space / 2x speedup over baseline". Example 2 is titled "Core thesis & key findings" — the exact user request phrasing.
- timestamp: 2026-10-29T00:00:02Z | `grep -rn "multidisciplinary|speedup|O(n log n)|Sustainable development"` matches only `core/prompt_budget.py` (plus an unrelated EVS test fixture). The resume never contained them; the prompt did.
- timestamp: 2026-10-29T00:00:03Z | `core/citation_validator.py:431-518` `auto_attribute_citations` appends `[E#]` to any sentence with lexical overlap >= 0.18 (one shared token for short sentences), so fabricated sentences inherit a real resume citation.
- timestamp: 2026-10-29T00:00:04Z | `core/citation_validator.py:402-427` sets `is_valid` from rank existence only; `support_precision` / `unsupported_ranks` are diagnostic and never gate rendering. `should_withhold_answer` ignores support.
- timestamp: 2026-10-29T00:00:05Z | `ui/views.py:611,742-746` falls back to `snippets[:3]` when no cited rank exists, pairing ungrounded/abstaining text with resume sources.
- timestamp: 2026-10-29T00:00:06Z | `ui/chat_controller.py:90-128` routes every prompt, including "Summarize the core thesis...", through the same QA retrieval/templating; summary intent is only partially caught by the extraction regex and has no distinct summary pipeline/system prompt.
- timestamp: 2026-10-29T00:00:07Z | `core/query_intent.py:45-74` has no summary-intent detector; `is_whole_document_query` may match "summarize ... findings" by accident but never guarantees document-wide coverage or page provenance.
- timestamp: 2026-10-29T00:00:08Z | `ui/views.py:646-654,775-782` labels any rank-valid answer "Grounded"; `main.py:526-529` unconditionally renders "100% Offline Local Pipeline" even when cloud mode is active; `main.py:543` uses emoji tab labels.
- timestamp: 2026-10-29T00:00:09Z | `core/local_llm.py:331` yields a "⚠️" emoji busy message; `ui/views.py:720` appends "▌" decoration during streaming.
- timestamp: 2026-10-29T00:00:10Z | Retrieval scoping itself is sound: `hybrid_retriever.search_hybrid` pushes `doc_id` into dense/FTS and re-filters as defense-in-depth; `fetch_document_chunks` returns page-ordered chunks for one document. Cross-document leakage is not the primary cause.

## Eliminated

- timestamp: 2026-10-29T00:00:11Z | Wrong/missing document ID: `ChatTurnService.prepare` passes the selected doc to `resolve_retrieval`; `HybridRetriever` filters server-side and again post-fusion.
- timestamp: 2026-10-29T00:00:12Z | Dropped document filter fallback: `search_hybrid`'s fallback applies the doc scope before limiting `k`.
- timestamp: 2026-10-29T00:00:13Z | Cross-document/cache reuse as the summary cause: `AiModel.reset_turn_state` exists and `ChatTurnService.finalize` receives the explicit per-turn `RetrievalResult`; the summary text matches the system prompt examples, not another document.
- timestamp: 2026-10-29T00:00:14Z | Corrupted indexed text: follow-up resume Q&A answered correctly from the same chunks, so indexing is intact.

## Resolution

**Root cause (confirmed).** Three independent defects combined:

1. `core/prompt_budget.py` `SYSTEM_GROUNDING_TEMPLATE` contained three worked examples whose
   answers were the exact observed hallucinations ("Environmental studies is multidisciplinary",
   "Sustainable development balances ecological protection and economic growth",
   "O(n log n) / O(n) space / 2x speedup"). One example was titled "Core thesis & key findings",
   the user's literal request. A 2B model reproduced them verbatim regardless of the document.
2. `core/citation_validator.py` `auto_attribute_citations` granted `[E#]` at overlap >= 0.18
   (one shared token), so fabricated sentences inherited a valid resume citation; and
   `is_valid` plus `should_withhold_answer` used rank existence only, so support never gated
   rendering.
3. Rendering was not tied to a verified grounding verdict: `ui/views.py` fell back to
   `snippets[:3]`, labelled rank-valid output "Grounded", and `main.py` asserted
   "100% Offline Local Pipeline" unconditionally. There was no summary-specific pipeline or
   intent detector, so summaries reused QA top-k retrieval and the contaminated QA prompt.

**Fixes.**

- `core/prompt_budget.py`: removed all worked examples; rewrote the 9-rule QA contract; added a
  dedicated `SUMMARY_SYSTEM_TEMPLATE`; `assemble_grounded_messages(..., system_template=...)`.
- `core/citation_validator.py`: added `GroundingStatus`
  (`grounded|partial|unsupported|abstained|ungrounded|invalid_citation|rank_only`),
  `support_verified`, support thresholds (0.5 withhold / 0.8 verified), and raised
  auto-attribution to overlap >= 0.5 with >= 2 shared tokens. Unsupported claims are withheld.
- `core/models.py`: added the frozen `GroundingReport` contract (request id, mode, scope,
  document ids, evidence count, cited/unsupported ranks, verification status/reason,
  auto-attributed count, incomplete context, regeneration attempted).
- `core/query_intent.py`: added `is_summary_request` (document-wide only; page/section-scoped
  requests stay on QA).
- `core/local_llm.py`: `mode: str = "qa"`; summary mode uses `SUMMARY_SYSTEM_TEMPLATE`, drops
  chat history, abstains when the scoped evidence set is empty; removed the emoji busy text.
- `ui/chat_controller.py`: document-wide summary retrieval (`fetch_document_chunks` +
  page-diverse selection + budget), `incomplete_context`, per-turn `GroundingReport`, and at
  most one bounded regeneration before abstaining.
- `ui/views.py`: grounding captions driven by `grounding_status` (never "grounded" for
  rank-only), no uncited-snippet fallback, cited-only sources panel, incomplete-context
  notices, duplicate-submit guard, document-switch scope reset, Summarizer length selector
  (concise/detailed) with cache keys including length, truthful Sources panel, Library-owned
  single upload flow, and Settings/Diagnostics split with a real connection test.
- `core/summarizer.py`: removed thesis/findings framing from profiles, added `length` plumbing
  to cache keys and map-reduce token budgets.
- `ui/components.py`, `ui/theme.py`, `main.py`: terminal-style real notifications, 960px
  centered column, 240-280px sidebar, single sidebar navigation (no emoji tabs, no duplicated
  in-content tabs), real session-scoped recent chats, New chat, Settings at the bottom, and
  provider status derived from the active provider (Local/Cloud + actual health).

**Tests.** New `tests/test_grounding_contract.py` (8 regressions: contaminated prompts absent,
summary contract separation, summary-intent scoping, fabricated sentence stays uncited,
supported sentence is attributed, unsupported citations withheld, rank-only never grounded).
Updated `tests/test_ui_redesign_apptest.py` and `tests/test_ui_smoke.py` for the new truthful
labels/colour tokens. Result: `453 passed`; `ruff check` clean; `ruff format --check` clean.

**Manual verification still required (not performed here).** Browser check that
`.st-key-terminal_notifications` styles correctly in Streamlit 1.42, the composer/sidebar
visual targets, and a live llama-server run of the resume scenario (deterministic mocks cover
the control flow, not live-model wording).

