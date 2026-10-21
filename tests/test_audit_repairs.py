"""Regression tests for the full-repository audit repairs.

Each test targets a root cause fixed during the audit: index path consistency,
silent vector loss, atomic ingestion rows, summary-cache invalidation, cloud
consent, sanitizer egress gaps, model identity, and bounded summarization.
"""

from pathlib import Path
import shutil

import pytest

from core.doc_store import DocStore
from core.model_identity import read_gguf_metadata, verify_local_model_pair
from core.models import Chunk, Document, EvidenceElement, Page, SummaryResult
from core.summarizer import MAX_BATCH_TOKENS, Summarizer
from ingestion.docling_reader import DoclingReader
from providers.groq_provider import GroqProvider
from retrieval.hybrid_retriever import DEFAULT_DB_URI, HybridRetriever, VectorIndexError
from ui.sanitizer import sanitize_markdown_for_local


REPO_ROOT = Path(__file__).resolve().parent.parent


def _doc(doc_id: str = "doc_audit_1", sha: str = "a" * 64) -> Document:
    return Document(
        doc_id=doc_id,
        filename="audit.pdf",
        sha256=sha,
        size_bytes=1024,
        num_pages=2,
        status="indexed",
        upload_time="2026-10-21T00:00:00Z",
        num_chunks=1,
    )


def test_default_index_lives_under_repo_data_directory() -> None:
    """The default index must match SQLite's data/ directory, not the package dir."""
    assert DEFAULT_DB_URI == REPO_ROOT / "data" / "lancedb"
    assert DEFAULT_DB_URI.parent.name == "data"
    assert DEFAULT_DB_URI.parent.parent == REPO_ROOT


def test_legacy_package_relative_index_is_copied_non_destructively(tmp_path, monkeypatch) -> None:
    """A legacy retrieval/data/lancedb index is copied to the canonical location."""
    import retrieval.hybrid_retriever as hr

    canonical = tmp_path / "data" / "lancedb"
    legacy = tmp_path / "retrieval" / "data" / "lancedb"
    legacy.mkdir(parents=True)
    (legacy / "fallback_store.json").write_text('{"documents": [], "vectors": []}', encoding="utf-8")

    monkeypatch.setattr(hr, "DEFAULT_DB_URI", canonical)
    monkeypatch.setattr(hr, "LEGACY_DB_URI", legacy)

    HybridRetriever()
    assert (canonical / "fallback_store.json").exists()
    assert (legacy / "fallback_store.json").exists(), "legacy source must not be deleted"


class _FailingTable:
    """Minimal LanceDB table stub whose write path always fails."""

    def merge_insert(self, *args, **kwargs):
        raise RuntimeError("simulated disk failure")


def test_index_chunks_raises_instead_of_silently_claiming_success(tmp_path) -> None:
    """A LanceDB write failure must surface to the caller, not return a success count."""
    retriever = HybridRetriever(db_uri=tmp_path / "lancedb")
    retriever._has_lancedb = True
    retriever._db = object()
    retriever._table = _FailingTable()

    chunk = Chunk(
        content="Vector loss regression chunk.",
        filename="x.pdf",
        page=1,
        chunk_id="chk_raise_1",
        doc_id="doc_raise",
    )
    with pytest.raises(VectorIndexError, match="Failed to persist"):
        retriever.index_chunks([chunk], embeddings=[[0.1] * 384])
    # A durable fallback copy is still written for recovery.
    assert (tmp_path / "lancedb" / "fallback_store.json").exists()


def test_record_ingestion_replaces_stale_children_atomically(tmp_path) -> None:
    """Re-ingesting a document removes stale pages/chunks/evidence rows."""
    store = DocStore(tmp_path / "atomic.db")
    doc = _doc()
    old_page = Page(doc_id=doc.doc_id, page_num=1, status="ok", char_count=10, num_chunks=1)
    old_chunk = Chunk(
        content="old chunk text",
        filename=doc.filename,
        page=1,
        chunk_id="chk_old",
        doc_id=doc.doc_id,
    )
    store.record_ingestion(doc, pages=[old_page], chunks=[old_chunk])

    new_page = Page(doc_id=doc.doc_id, page_num=2, status="ok", char_count=20, num_chunks=1)
    new_chunk = Chunk(
        content="new chunk text",
        filename=doc.filename,
        page=2,
        chunk_id="chk_new",
        doc_id=doc.doc_id,
    )
    evidence = EvidenceElement(
        element_id="elem_new",
        doc_id=doc.doc_id,
        page=2,
        kind="table",
        content="| a | b |",
        source="docling",
        model_version="",
    )
    store.record_ingestion(doc, pages=[new_page], chunks=[new_chunk], evidence=[evidence])

    chunk_ids = [c.chunk_id for c in store.get_chunks_for_doc(doc.doc_id)]
    assert chunk_ids == ["chk_new"]
    assert [p.page_num for p in store.get_pages_for_doc(doc.doc_id)] == [2]
    assert [e.element_id for e in store.get_evidence_for_doc(doc.doc_id)] == ["elem_new"]


def test_summary_cache_rejects_empty_legacy_version(tmp_path) -> None:
    """A summary stored without a version is stale when a version is requested."""
    store = DocStore(tmp_path / "summary_version.db")
    doc = _doc(sha="b" * 64)
    store.upsert_document(doc)
    store.save_summary(
        SummaryResult(
            summary_id="summ_legacy",
            doc_id=doc.doc_id,
            sha256=doc.sha256,
            profile="overview",
            summary_text="Legacy text",
            page_references=[1],
            created_at="2026-10-21T00:00:00Z",
            model_version="",
        )
    )
    assert store.get_summary(doc.sha256, "overview", model_version="qwen2-vl-2b:docling-1000-200-v1") is None
    assert store.get_summary(doc.sha256, "overview") is not None


def test_groq_provider_requires_explicit_consent() -> None:
    """Cloud adapters must refuse generation without per-transmission consent."""
    provider = GroqProvider(api_key="gsk_test", user_consented=False)
    with pytest.raises(PermissionError, match="explicit user consent"):
        provider.generate_text("summarize")
    with pytest.raises(PermissionError, match="explicit user consent"):
        list(provider.stream_text("summarize"))


def test_sanitizer_blocks_bare_urls_autolinks_and_reference_definitions() -> None:
    """Local mode must neutralize every Markdown form that can trigger egress."""
    raw = (
        "Bare https://tracking.example/pixel and <https://auto.example/x>.\n"
        "[label][ref]\n\n[ref]: https://ref.example/target\n"
        "<video src='https://evil.example/x.mp4'></video>\n"
    )
    cleaned = sanitize_markdown_for_local(raw)
    assert "tracking.example" not in cleaned
    assert "auto.example" not in cleaned
    assert "ref.example" not in cleaned
    assert "evil.example" not in cleaned
    assert "[external link blocked]" in cleaned


def test_sanitizer_allows_external_links_in_consented_cloud_mode() -> None:
    """Consented cloud mode keeps user-facing links intact."""
    raw = "See [source](https://example.com/paper)."
    assert "https://example.com/paper" in sanitize_markdown_for_local(raw, allow_external=True)


def test_summarizer_splits_oversized_page_into_bounded_batches() -> None:
    """A single huge page must not produce an over-budget map prompt."""
    page = Page(
        doc_id="doc_big",
        page_num=7,
        status="ok",
        char_count=40_000,
        page_text="word " * 8_000,
    )
    summarizer = Summarizer(provider=object())  # bundling does not call the provider
    batches = summarizer._bundle_pages([page], max_tokens=MAX_BATCH_TOKENS)
    assert len(batches) > 1
    for batch in batches:
        assert sum(len((p.page_text or "")) // 4 for p in batch) <= MAX_BATCH_TOKENS + 8
        assert all(p.page_num == 7 for p in batch)


def test_long_markdown_table_split_repeats_header() -> None:
    """Long tables are split by rows and keep the header in every chunk."""
    rows = "\n".join(f"| {i} | value-{i} |" for i in range(200))
    table = f"| id | value |\n|---|---|\n{rows}"
    chunks = DoclingReader._split_table_markdown(table, max_chars=600)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.splitlines()[0] == "| id | value |"
        assert chunk.splitlines()[1] == "|---|---|"
        assert len(chunk) <= 700


@pytest.mark.skipif(
    not (REPO_ROOT / "models" / "qwen3-vl-2b-instruct-q4_k_m.gguf").exists(),
    reason="local GGUF artifacts are not installed",
)
def test_local_model_identity_matches_declared_architecture() -> None:
    """The shipped files must be a compatible Qwen-VL LM/projector pair."""
    lm_path = REPO_ROOT / "models" / "qwen3-vl-2b-instruct-q4_k_m.gguf"
    proj_path = REPO_ROOT / "models" / "mmproj-f16.gguf"
    lm = read_gguf_metadata(lm_path)
    assert lm.architecture == "qwen2vl"
    assert verify_local_model_pair(lm_path, proj_path) == []


def test_lifecycle_delete_aborts_before_sqlite_on_vector_failure(tmp_path) -> None:
    """A vector deletion failure must leave the SQLite row intact for retry."""
    from ui.lifecycle_service import LifecycleService

    class FailingRetriever:
        def delete_document(self, doc_id):
            raise VectorIndexError("simulated vector failure")

    store = DocStore(tmp_path / "lifecycle.db")
    doc = _doc()
    store.upsert_document(doc)

    service = LifecycleService(doc_store=store, hybrid_retriever=FailingRetriever(), cache_dir=tmp_path / ".cache")
    with pytest.raises(VectorIndexError):
        service.delete_document(doc.doc_id)
    assert store.get_document(doc.doc_id) is not None


def test_purge_reports_vector_failure_but_clears_session_state(tmp_path) -> None:
    """Purge surfaces tier failures instead of reporting a silent success."""
    from ui.lifecycle_service import LifecycleService

    class FailingRetriever:
        def purge_all(self):
            raise VectorIndexError("simulated purge failure")

    store = DocStore(tmp_path / "purge.db")
    store.upsert_document(_doc())
    cache = tmp_path / ".cache"
    cache.mkdir()
    shutil.copy(REPO_ROOT / "README.md", cache / "marker.txt")

    class Session(dict):
        def __getattr__(self, name):
            return self.get(name)

    session = Session(doc_ids={"doc_audit_1"}, failed_doc_ids=set(), indexed_files={"audit.pdf"}, document_metadata={})
    service = LifecycleService(doc_store=store, hybrid_retriever=FailingRetriever(), cache_dir=cache)
    with pytest.raises(RuntimeError, match="Purge incomplete"):
        service.purge_all(session_state=session)
    assert store.count_documents() == 0
    assert session["doc_ids"] == set()
