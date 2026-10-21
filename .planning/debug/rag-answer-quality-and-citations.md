# Debug Session: RAG Answer Quality, Poor Retrieval, and 0% Citation Precision

## Status: Resolved

## Symptoms
- When asking "Summarize the core thesis and key findings of the document", "what does the EVS.pdf say?", or "give me the questions":
  - The model returned single-sentence, uninformative answers (e.g. "The questions are organized by paper and question number.").
  - "Unverified Citations (0% citation precision)" was displayed on every response.
  - The retrieved context chips mixed unrelated documents and were limited to page 1 fragments.
  - The user observed: "idk if its the UI that's faulty, but the answer's really aren't coming out."

## Root Cause Analysis
1. **Docling Reader Chunk Over-Fragmentation:**
   - In `docling_reader.py`, `iterate_items()` iterates over individual items (headers, list items, single lines).
   - Calling `text_splitter.split_text(item)` on each item separately caused every header ("Causes:", "Control:", "Importance:", "1. Introduction") and every individual bullet point to be stored as an isolated chunk.
   - An 11-page PDF produced 263 chunks (averaging 79 characters / 15 words per chunk; 74% were under 100 characters).
   - When vector-embedded, short phrases like "Causes:" or "1. Introduction" produced high spurious cosine similarity and dominated the candidate pool, while the actual questions and answers were fragmented across dozens of disconnected chunks.
   - For `k=5`, the model received ~200-300 characters total of disconnected text, leaving it with almost zero information to answer the questions.

2. **Naive Query Contextualization Corrupting Multi-Turn Queries:**
   - In `ui/views.py` and `local_llm.py`:
     `search_query = f"{last_user_msgs[-1]} {effective_prompt}"`
   - Every subsequent question had the entire previous question blindly prepended to it.
   - Turn 1: "Summarize the core thesis..."
   - Turn 2: "what does the EVS.pdf say?" -> became `"Summarize the core thesis and key findings of the document. what does the EVS.pdf say?"`, retrieving chunks from Manoj CN REPORT.pdf!
   - Turn 3: "give me the questions" -> became `"what does the EVS.pdf say? give me the questions"`, which matched only page 1 of EVS.pdf in BM25.

3. **Restricted Retrieval Candidate Pool & Top-K Depth:**
   - `k=5` in `ui/views.py` and `candidate_pool = max(k * 4 if doc_id else k * 2, 10)` in `hybrid_retriever.py` yielded only 10 candidates for dense and FTS search. Across 402 chunks and multiple documents, 10 candidates was too shallow for RRF fusion.

4. **Missing Few-Shot Citation Example in System Grounding Template:**
   - The local 2B model omitted inline `[E#]` citations when not shown a concrete example format.
   - Because `total_citations == 0`, `citation_validator.py` returned `precision = 0.0`.
   - The UI then labeled the response "Unverified Citations (0% citation precision)" and displayed all 5 candidate snippets as chips, creating the false appearance that the assistant generated hallucinated citations.

5. **Lack of Target Document Auto-Detection in UI:**
   - When the user explicitly asked "what does the EVS.pdf say?" while "All Documents" was selected, retrieval searched across all documents without prioritizing `EVS.pdf`.

## Fixes Implemented
1. **Coalesced Chunking in `docling_reader.py`:**
   - Group consecutive non-table items on each page into coherent text blocks before splitting with `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`.
   - Standalone markdown tables remain intact as dedicated table chunks.
   - Reduced `EVS.pdf` from 263 fragmented crumbs to 30 rich, coherent chunks (~800-1000 characters each) containing complete questions, definitions, and explanations together.
   - Reduced `Manoj CN REPORT.pdf` from 139 crumbs to 19 rich chunks.
   - Re-indexed existing documents in SQLite and LanceDB.

2. **Smart Query Contextualization in `ui/views.py` & `local_llm.py`:**
   - Only contextualize `search_query` when the user prompt is an ambiguous short follow-up (<= 4 tokens with pronouns like "it", "that", "why", "more").
   - Standalone queries are preserved directly, eliminating query pollution across turns.

3. **Target Document Auto-Detection in `ui/views.py`:**
   - If the user names an active document (e.g. "in EVS.pdf", "what does EVS say?"), automatically set `doc_filter` to that document ID.

4. **Increased Retrieval Top-K and Candidate Pool:**
   - Increased `k` to 8 in `ui/views.py`.
   - Increased `candidate_pool` in `hybrid_retriever.py` to `max(k * 5 if doc_id else k * 4, 30)`.

5. **Prompt Budget & Citation Formatting Example in `prompt_budget.py`:**
   - Added Rule 4 ("Provide comprehensive, detailed answers...") and an explicit `CITATION FORMAT EXAMPLE` showing inline `[E1]`, `[E2]` citation structure to guide 2B models.

6. **Refined Grounding and Citation Chip Rendering in `ui/views.py`:**
   - Distinguished "Ungrounded response — no evidence citations ([E#]) were included" from actual invalid citations.
   - Highlight and display chips for cited ranks (`verification.cited_ranks`), and label the expander accordingly.

## Verification
- Ran full test suite: **296 passed in 38.91s**.
- Tested retrieval with the exact user queries:
  - "what does the EVS.pdf say?": All top snippets retrieved from `EVS.pdf` with full questions, definitions, and ozone facts.
  - "give me the questions": Retrieved Page 2 questions (Question 1(A), Question 1(B)) and unit preparation notes.
  - "Summarize the core thesis and key findings": Retrieved rich multi-paragraph summaries of ring topology.
