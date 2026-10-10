# Phase 0: Baseline and Audit - Research

**Researched:** 2026-10-10  
**Domain:** Baseline benchmarking, regression testing harnesses (Pytest), and test corpus construction for Python RAG systems  
**Confidence:** HIGH  

<user_constraints>
## User Constraints (from CONTEXT.md & User Requests)

### Locked Decisions
- No `CONTEXT.md` exists — user chose to plan directly using requirements and codebase maps.
- **Rule 1 (Git Commits):** Proper atomic git commits per planning, execution, review, and verification phases.
- **Rule 2 (Codebase Map Grounding):** Agents must inspect `.planning/codebase/` documents (`ARCHITECTURE.md`, `CONCERNS.md`, `CONVENTIONS.md`, `INTEGRATIONS.md`, `STACK.md`, `STRUCTURE.md`, `TESTING.md`) before planning and execution.
- **Rule 3 (Quality & CI/CD):** Proper test suites must be created and updated, CI/CD pipelines synchronized, and `CONCERNS.md` kept in check across every phase as codebase evolves.

### Claude's Discretion
- Choice of initial test corpus structure and test fixtures.
- Test runner configuration (`pytest`, `conftest.py`, pytest markers).
- Performance baseline benchmarking script format and metric logging.
- GitHub Actions CI workflow structure.

### Deferred Ideas (OUT OF SCOPE)
- End-to-end VLM local GPU testing (deferred to Phase 2 when llama-server is deployed).
- Docling and LanceDB testing (deferred to Phases 3 and 4 when those libraries are installed).
</user_constraints>

<research_summary>
## Summary

Phase 0 sets the empirical and quality foundation for the entire project. The existing codebase (`main.py`, `local_llm.py`, `local_embedding.py`, `vector_index.py`, `pdf_reader.py`) currently has zero automated tests, zero CI/CD workflows, no synthetic test corpus, and five documented critical risks in `CONCERNS.md`.

To establish a solid baseline without breaking existing functionality:
1. **Pytest Harness:** Introduce `pytest>=8.3.0` and `pytest-mock` configured via `pyproject.toml` or `pytest.ini`. Create a clean `tests/` directory with fixtures for synthetic in-memory PDFs and mocked Groq/Sentence-Transformers responses (as specified in `TESTING.md`).
2. **Representative Test Corpus:** Assemble a dedicated `tests/data/corpus/` directory with synthetic and real representative PDFs covering 6 essential categories: clean digital text, scanned/low-text, multi-column layout, table-heavy, visual/chart-heavy, and malformed/non-PDF files.
3. **Baseline Benchmarks:** Build a deterministic benchmark script (`scripts/benchmark_baseline.py`) that profiles extraction throughput, memory usage, and vector search latency of the current `pypdf` + `SentenceTransformer` + `VectorIndex` pipeline.
4. **CI/CD Synchronization:** Create `.github/workflows/ci.yml` running pytest and ruff lint checks on Python 3.11 on every push and pull request.

**Primary recommendation:** Establish the test directory, synthetic test corpus fixtures, and unit tests for existing pure-logic components (`VectorIndex`, `PdfReader`) first, measure current baseline performance, and set up GitHub Actions CI before any architectural rewrites begin.
</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| **pytest** | `>=8.3.0` | Test runner & framework | Standard Python testing tool with fixture scoping and clear assertion diffs. |
| **pytest-mock** | `>=3.14.0` | Mocking wrapper | Clean wrapper around Python stdlib `unittest.mock` for isolating external APIs. |
| **reportlab** | `>=4.2.0` | Programmatic PDF generation | Used in test fixtures to deterministically generate synthetic digital, multi-column, and table PDFs. |
| **ruff** | `>=0.9.0` | Linter & formatter | Blazing-fast code style and syntax checks for CI quality gate. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **psutil** | `>=6.1.0` | Process resource profiling | Measuring RAM and CPU memory during baseline benchmarking. |
| **pytest-cov** | `>=6.0.0` | Code coverage | Measuring test suite coverage across codebase modules. |

**Installation:**
```bash
pip install "pytest>=8.3.0" "pytest-mock>=3.14.0" "reportlab>=4.2.0" "ruff>=0.9.0" "psutil>=6.1.0"
```
</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Test Directory Layout
```
tests/
├── __init__.py
├── conftest.py                # Shared fixtures (synthetic PDFs, mock Groq, mock embeddings)
├── test_vector_index.py       # Unit tests for pure-python VectorIndex distance math & guards
├── test_pdf_reader.py         # Unit tests for PdfReader text extraction & chunk overlap
├── test_local_embedding.py    # Unit tests for LocalEmbedding with stubbed SentenceTransformer
├── test_local_llm.py          # Unit tests for AiModel prompt assembly & mock streaming
└── data/
    └── corpus/                # Representative test PDFs
        ├── clean_digital.pdf
        ├── multi_column.pdf
        ├── dense_table.pdf
        ├── scanned_sample.pdf
        ├── chart_diagram.pdf
        └── corrupt_invalid.pdf
scripts/
└── benchmark_baseline.py      # Standalone reproducible baseline profiling script
.github/
└── workflows/
    └── ci.yml                 # GitHub Actions CI workflow
```

### Pattern 1: Deterministic Synthetic Test PDF Fixtures
**What:** Using `reportlab` or raw PDF byte generators in `conftest.py` to create reproducible PDF fixtures on-the-fly or saved in `tests/data/corpus/`.  
**Why:** Eliminates dependency on external copyright-encumbered documents; ensures exact known text, tables, and page counts for assertion matching.

**Example:**
```python
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def create_synthetic_pdf(text: str, pages: int = 1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for p in range(pages):
        c.drawString(72, 750, f"Page {p + 1}")
        c.drawString(72, 700, f"{text} (page {p + 1})")
        c.showPage()
    c.save()
    return buf.getvalue()
```

### Pattern 2: Seam Mocking for External Inference & Embeddings
**What:** Mocking `groq.Groq` and `SentenceTransformer` at import/class boundaries as documented in `TESTING.md`.  
**Why:** Unit tests run in milliseconds offline without API keys or GPU memory.

**Example:**
```python
def test_vector_search_pure_math():
    idx = VectorIndex(vector_dim=3, distance_metric="cosine")
    idx.add_vector([1.0, 0.0, 0.0], {"doc": "A"})
    idx.add_vector([0.0, 1.0, 0.0], {"doc": "B"})
    results = idx.search([1.0, 0.0, 0.0], k=1)
    assert len(results) == 1
    assert results[0][0]["doc"] == "A"
    assert results[0][1] == 0.0  # Cosine distance to identical vector is 0
```
</architecture_patterns>

<pitfalls_mitigation>
## Codebase Map Alignment & Pitfalls Mitigation

### Alignment with `.planning/codebase/`:
1. **`ARCHITECTURE.md`:** Acknowledges the Streamlit `main.py` entry point, `PdfReader` text extraction, `LocalEmbedding` sentence-transformers integration, and in-memory `VectorIndex`. Baseline tests will exercise these components without modifying their current public APIs.
2. **`CONCERNS.md`:** 
   - *Risk 1 (Groq API failures):* Baseline tests will assert that missing API keys or mock exceptions are properly trapped rather than silently crashing.
   - *Risk 2 (In-memory data loss & per-session models):* Tests will verify that `VectorIndex` states can be cleanly isolated in tests.
   - *Risk 3 (Unbounded uploads & non-PDF files):* Tests will assert behavior when handling malformed or non-PDF bytes.
   - *Risk 4 (Filename-keyed dedup):* Test will capture existing filename dedup limitation so Phase 1 can verify SHA-256 fix.
   - *Risk 5 (Divergent retrieval contexts):* Test will capture context assembly logic in `AiModel.ask_a_question_from_pdf_stream`.
3. **`CONVENTIONS.md`:** All new test files will follow 4-space indentation, `snake_case` test functions (`test_*`), explicit typing, and section comment banners.
4. **`TESTING.md`:** Directly implements the suggested test organization (`tests/test_vector_index.py`, `tests/test_pdf_reader.py`, etc.) and the mocking seams recommended in `TESTING.md:48-57`.
5. **`INTEGRATIONS.md`:** Stubs out `groq` and `sentence_transformers` in tests to ensure 100% offline test execution.
</pitfalls_mitigation>

<baseline_metrics>
## Baseline Metrics Target

The baseline benchmarking script (`scripts/benchmark_baseline.py`) will record and log:
1. **PDF Text Extraction Latency:** Milliseconds per page with `pypdf.PdfReader`.
2. **Chunk Generation Count:** Number of chunks produced by `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`.
3. **Embedding Generation Latency:** Batch embedding latency with `SentenceTransformer("all-MiniLM-L6-v2")` on CPU.
4. **Vector Search Latency:** Search latency for `VectorIndex.search(k=10)` across 100, 500, and 1,000 synthetic chunks.
5. **Peak Process RAM:** RSS memory overhead before and after loading the embedding model.
</baseline_metrics>

---
*Phase 0 Research complete*  
*Ready for planning: yes*
