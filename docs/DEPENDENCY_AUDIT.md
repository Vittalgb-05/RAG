# Dependency Audit — 2026-10-29

**Scope:** every direct dependency in `requirements.txt` plus the packages that constrain
them. Versions were read from the working environment (`importlib.metadata`), latest
available versions from the PyPI JSON API, and constraints from each package's published
`requires_dist`. Nothing here was upgraded on the strength of a version number alone.

**Python support:** the project targets 3.11+ (`pyproject.toml`, CI on 3.11); the audit
host runs 3.13.5. The lockfile is compiled with `--universal --python-version 3.11`.

## Decisions

| Package | Before | After | Latest checked | Reason |
|---|---|---|---|---|
| `streamlit` | 1.42.0 | **1.66.1** | 1.66.1 | Requested upgrade to the current stable release. Breaking changes handled in code/tests (see below). |
| `pypdf` | 5.3.0 | **6.21.4** | 6.21.4 | Two lines of fixes since 5.3; the reader/validator paths (`ingestion/pdf_reader.py`, `ingestion/upload_validation.py`) are covered by `test_pdf_reader`, `test_upload_validation` and passed unchanged on 6.21.4. |
| `pymupdf` | `>=1.24.0` | `>=1.24.0,<2.0` | 2.0 | 2.0 is a new major line with no regression run against the rasterization/crop paths. The open-ended range would silently install it, so the ceiling now matches what is verified (1.28.2). |
| `pillow` | `>=10.2.0` | `>=10.2.0,<13` | 13.0.0 | Ceiling is imposed upstream: `docling-core`, `docling-ibm-models`, and `docling-parse` all declare `pillow<13.0.0`. Installed 13.0.0 was reverted to the lockfile's 11.3.0. |
| `docling` | `>=2.0.0` | unchanged | 2.144.0 | Locked at 2.138.0. Docling changes extraction output, which would invalidate cached chunk hashes and change grounding behaviour; no defect motivates the bump. |
| `lancedb` / `pyarrow` | `>=0.17.0` / `>=14.0.0` | unchanged | 0.40.0 / 26.0.0 | LanceDB 0.40.0 is already current; pyarrow is constrained by LanceDB. Retrieval tests pass as-is. |
| `pydantic` | `==2.11.9` | unchanged | 2.14.1 | Exact pin already works and the models use `extra="forbid"`; no driver to move. |
| `httpx` | `==0.28.1` | unchanged | 0.28.1 | Already current. |
| `sentence-transformers` | `==3.4.1` | unchanged | 6.2.0 | Three major versions ahead. Embeddings are persisted in LanceDB, so a version change risks silently altering vectors for already-indexed documents. Deferred deliberately. |
| `numpy` | `>=1.26,<3.0` | unchanged | 2.5.4 | 2.5.x requires Python ≥3.12 while the project supports 3.11; the existing range stays. |
| `groq` | `==0.15.0` | unchanged | 1.7.0 | Optional cloud fallback, major-version jump, no defect. Deferred. |
| `litellm` | `>=1.50.0` | unchanged | 1.106.5 | Lockfile already resolves 1.105.0; consent gate and key scrubbing are version-agnostic. |
| `langchain-text-splitters` | `==0.3.6` | unchanged | 1.1.3 | Only `RecursiveCharacterTextSplitter` semantics matter; a major bump would change chunk boundaries and therefore citation granularity. |
| `psutil` | `==6.1.1` | unchanged | 7.2.2 | Telemetry only; no need to move a major. |
| `rapidocr` / `rapidocr-onnxruntime` | range-split by Python | unchanged | 3.10.0 / 1.4.4 | Both branches already resolve to current releases. |
| `pytest`, `ruff`, `reportlab` (test-only) | `>=8.3`, `>=0.9`, `>=4.2` | unchanged | 9.2.0 / 0.17.3 / 5.1.0 | Formatting/lint behaviour changes would produce unrelated churn; not required by this task. |

## Transitive effects worth noting

- `streamlit` 1.66.1 requires `uvicorn<1,>=0.30` and `pandas<4`, which the regenerated
  lockfile picks up. No conflict with LanceDB, Docling, or LiteLLM.
- `protobuf`, `transformers`, `tokenizers`, `torch` are pulled by Docling /
  sentence-transformers and stay at their previously locked versions.

## Breaking changes handled for Streamlit 1.66.1

1. `AppTest.from_file("main.py")` now resolves relative paths against the *calling test
   file*, not the working directory. `tests/test_ui_redesign_apptest.py` passes an
   absolute path.
2. Accessing `st.secrets` outside a script run context raises `RuntimeError` instead of
   returning `None`. `providers/groq_provider.py` now catches it so constructing a
   provider from tests or a CLI still degrades to the environment variable.

## Verification

```bash
uv pip compile --universal --python-version 3.11 requirements.txt -o requirements-lock.txt
# clean-room resolution (metadata only, nothing installed):
uv pip install --python <fresh-venv>/Scripts/python.exe --dry-run \
  -r requirements-lock.txt -r requirements-test.txt
python -m pytest -q          # 479 passed
python -m ruff check .
python -m ruff format --check .
```

`python setup.py install_dependencies` and the Docker/CI jobs consume
`requirements-lock.txt`, so the regenerated lockfile is the single source for pinned
installs. `pip install -e .` reads `requirements.txt` (via `setup.py`), which is why the
two upper bounds above are expressed there rather than only in the lockfile.
