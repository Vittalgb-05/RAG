"""Unit tests for hierarchical multi-profile document summarizer service."""

from collections.abc import Generator
import pytest
from doc_store import DocStore
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities
from models import Document, Page, SummaryResult
from summarizer import (
    FAST_PATH_TOKEN_LIMIT,
    PROFILE_SYSTEM_INSTRUCTIONS,
    Summarizer,
    extract_page_references,
)


class MockSummarizerProvider(BaseModelProvider):
    """Mock provider recording calls and returning deterministic summary responses."""

    def __init__(self, model_name: str = "mock-qwen-2b") -> None:
        self._model_name = model_name
        self.generate_calls: list[dict[str, object]] = []

    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="Mock healthy", provider_type="local")

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            model_name=self._model_name,
            context_window=4096,
            supports_vision=False,
            is_local=True,
            supports_streaming=True,
        )

    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> str:
        self.generate_calls.append(
            {
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )

        # Map response pattern
        if "intermediate analytical summary" in prompt:
            return "- Key insight from these pages (p. 1) and (p. 2)."

        # Reduce response pattern
        if "synthesizing multiple intermediate" in prompt:
            return "# Comprehensive Synthesis\n\nExecutive findings (p. 1), (p. 2), and (p. 3)."

        # Single pass default
        return "## Executive Overview\n\nCore thesis and findings (p. 1) and (p. 2)."

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        yield "mock stream"

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str = "Describe this image",
        max_tokens: int = 512,
    ) -> str:
        return "mock visual element"


def test_extract_page_references():
    """Verify regex extraction, deduplication, and sorting of source page citations."""
    sample = "Findings reported on (p. 3) and (p. 1). Additional metrics in (Page 4) and p. 2. Invalid p. 0 ignored."
    pages = extract_page_references(sample)
    assert pages == [1, 2, 3, 4]

    # No citations returns empty list
    assert extract_page_references("No citations present here.") == []


def test_summarize_document_single_pass():
    """Verify single-pass fast path for short documents within token threshold."""
    provider = MockSummarizerProvider()
    summarizer = Summarizer(provider=provider)

    pages = [
        Page(doc_id="doc_test1", page_num=1, status="ok", char_count=200, page_text="Introduction to RAG (p. 1)."),
        Page(doc_id="doc_test1", page_num=2, status="ok", char_count=200, page_text="Architecture and benchmarks."),
    ]

    res = summarizer.summarize_document(
        doc_id="doc_test1",
        sha256="1" * 64,
        pages=pages,
        profile="overview",
    )

    assert isinstance(res, SummaryResult)
    assert res.doc_id == "doc_test1"
    assert res.sha256 == "1" * 64
    assert res.profile == "overview"
    assert res.cached is False
    assert res.page_references == [1, 2]
    assert len(provider.generate_calls) == 1
    assert "Executive Overview" in res.summary_text


def test_all_five_summary_profiles():
    """Verify all 5 canonical profiles use their distinct system instructions."""
    for profile in ["overview", "detailed", "study_notes", "tables_figures", "findings"]:
        provider = MockSummarizerProvider()
        summarizer = Summarizer(provider=provider)
        pages = [
            Page(doc_id="doc_prof", page_num=1, status="ok", char_count=100, page_text="Content for profile testing.")
        ]

        res = summarizer.summarize_document(
            doc_id="doc_prof",
            sha256="a" * 64,
            pages=pages,
            profile=profile,
        )
        assert res.profile == profile
        assert len(provider.generate_calls) == 1
        expected_instruction = PROFILE_SYSTEM_INSTRUCTIONS[profile]
        assert provider.generate_calls[0]["system_prompt"] == expected_instruction


def test_unknown_profile_raises_error():
    """Verify invalid profile name raises ValueError."""
    provider = MockSummarizerProvider()
    summarizer = Summarizer(provider=provider)
    pages = [Page(doc_id="doc_err", page_num=1, status="ok", char_count=100, page_text="Text")]

    with pytest.raises(ValueError, match="Unknown summary profile 'invalid'"):
        summarizer.summarize_document(
            doc_id="doc_err",
            sha256="b" * 64,
            pages=pages,
            profile="invalid",
        )


def test_summarize_document_map_reduce():
    """Verify multi-page large documents trigger sequential map-reduce pipeline."""
    provider = MockSummarizerProvider()
    summarizer = Summarizer(provider=provider)

    # Create 8 pages with large text to comfortably exceed FAST_PATH_TOKEN_LIMIT (2500 tokens)
    large_text = "Dense technical prose regarding multimodal retrieval systems. " * 80  # ~800 words (~1000 tokens)
    pages = [
        Page(
            doc_id="doc_large",
            page_num=i,
            status="ok",
            char_count=len(large_text),
            page_text=f"Page {i}: {large_text}",
        )
        for i in range(1, 6)
    ]

    res = summarizer.summarize_document(
        doc_id="doc_large",
        sha256="c" * 64,
        pages=pages,
        profile="detailed",
    )

    assert isinstance(res, SummaryResult)
    # Must have called map stage for batches + reduce stage (at least 2 calls)
    assert len(provider.generate_calls) >= 2
    assert res.cached is False
    assert 1 in res.page_references
    assert 2 in res.page_references


def test_summarize_document_caching_lifecycle(tmp_path):
    """Verify summary persistence in DocStore, cache hit on repeat, and force_refresh bypass."""
    db_file = tmp_path / "summarizer_cache.db"
    store = DocStore(db_file)

    doc_id = "doc_cached_1"
    sha = "f" * 64
    store.upsert_document(
        Document(
            doc_id=doc_id,
            filename="cached.pdf",
            sha256=sha,
            size_bytes=4096,
            num_pages=2,
            status="indexed",
            upload_time="2026-10-11T12:00:00Z",
        )
    )

    provider = MockSummarizerProvider()
    summarizer = Summarizer(provider=provider, doc_store=store)

    pages = [
        Page(doc_id=doc_id, page_num=1, status="ok", char_count=200, page_text="Page 1 text."),
        Page(doc_id=doc_id, page_num=2, status="ok", char_count=200, page_text="Page 2 text."),
    ]

    # 1. Cold call: Cache miss, invokes provider
    first_res = summarizer.summarize_document(
        doc_id=doc_id,
        sha256=sha,
        pages=pages,
        profile="overview",
    )
    assert first_res.cached is False
    assert len(provider.generate_calls) == 1

    # 2. Warm call: Cache hit, ZERO provider invocations
    second_res = summarizer.summarize_document(
        doc_id=doc_id,
        sha256=sha,
        pages=pages,
        profile="overview",
    )
    assert second_res.cached is True
    assert second_res.summary_id == first_res.summary_id
    assert second_res.summary_text == first_res.summary_text
    assert len(provider.generate_calls) == 1  # Still 1, not incremented!

    # 3. Force refresh: Bypasses cache, calls provider again
    refreshed_res = summarizer.summarize_document(
        doc_id=doc_id,
        sha256=sha,
        pages=pages,
        profile="overview",
        force_refresh=True,
    )
    assert refreshed_res.cached is False
    assert len(provider.generate_calls) == 2  # Incremented to 2!
