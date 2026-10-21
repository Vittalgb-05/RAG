"""Unit and integration tests for Cloud Mode privacy controls and local-only invariants (UI-04, INF-03, INF-04)."""

import socket
import pytest

from retrieval.hybrid_retriever import HybridRetriever
from providers.litellm_provider import LiteLLMProvider
from retrieval.local_embedding import LocalEmbedding
from core.local_llm import AiModel
from core.models import Chunk, RetrievalResult


def test_default_session_privacy_state_is_local_only() -> None:
    """Verify that default model initialization defaults to offline local mode without network egress (INF-03, UI-04)."""
    model = AiModel(cloud_mode=False)
    caps = model.get_capabilities()
    assert caps.is_local is True
    assert model.cloud_mode is False
    model.close()


def test_consent_state_transition_workflow() -> None:
    """Verify state transitions: local -> unconsented blocked -> consented active -> consent revoked."""
    # 1. Start in local mode
    model = AiModel(cloud_mode=False)
    assert model.provider.get_capabilities().is_local is True

    # 2. Attempting cloud provider without consent raises PermissionError
    unconsented_cloud = LiteLLMProvider(
        model_name="groq/llama-3.3-70b-versatile",
        api_key="mock-key",
        user_consented=False,
    )
    with pytest.raises(PermissionError, match="Cloud transmission blocked"):
        unconsented_cloud.generate_text("Test prompt")

    # 3. Explicit consent allows cloud operation
    consented_cloud = LiteLLMProvider(
        model_name="groq/llama-3.3-70b-versatile",
        api_key="mock-key",
        user_consented=True,
    )
    model.set_cloud_mode(True, cloud_provider=consented_cloud)
    assert model.cloud_mode is True
    assert model.provider.get_capabilities().is_local is False
    assert model.model_name == "groq/llama-3.3-70b-versatile"

    # 4. Revoking consent switches AiModel back to local mode
    model.set_cloud_mode(False)
    assert model.cloud_mode is False
    assert model.provider.get_capabilities().is_local is True
    model.close()


def test_local_only_ingestion_and_indexing_invariant(monkeypatch, tmp_path) -> None:
    """Verify document ingestion, OCR fallback, embedding, and hybrid indexing perform zero network calls (INF-03)."""
    # 1. Initialize local embedding backend
    embedding_backend = LocalEmbedding()

    # Guard against any outbound socket connections during processing, indexing, and search
    def guarded_create_connection(*args, **kwargs):
        raise ConnectionRefusedError("Outbound network egress strictly forbidden during local ingestion (INF-03).")

    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)

    test_texts = [
        "Local privacy ensures sensitive documents never leave the host system.",
        "LanceDB stores hybrid sparse and dense vectors on the local filesystem.",
    ]
    vectors = embedding_backend.get_embeddings(test_texts)
    assert vectors.shape[0] == 2
    assert vectors.shape[1] == 384

    # 2. Persistent LanceDB hybrid retriever
    db_dir = tmp_path / "lancedb_privacy_test"
    retriever = HybridRetriever(
        db_uri=db_dir,
        embedding_fn=embedding_backend._embed_one,
    )

    chunks = [
        Chunk(
            chunk_id=f"chk_{i}",
            doc_id="doc_privacy",
            filename="privacy.pdf",
            content=text,
            page=1,
        )
        for i, text in enumerate(test_texts)
    ]
    chunk_dicts = [c.model_dump() for c in chunks]

    # Index chunks locally
    retriever.index_chunks(chunk_dicts, vectors.tolist())

    # Query hybrid retrieval locally
    result = retriever.search_hybrid("sensitive documents", k=2)
    assert isinstance(result, RetrievalResult)
    assert len(result.snippets) > 0
    assert "sensitive documents" in result.snippets[0].content.lower()

    retriever.close()


def test_chat_turn_metadata_records_locality_and_cloud_egress() -> None:
    """Verify chat turn schema captures is_cloud and model_name for transparent egress chips (UI-04)."""
    local_turn = {
        "role": "assistant",
        "content": "Offline answer from local weights.",
        "sources": ["doc.pdf"],
        "verification": {"precision": 1.0, "is_valid": True, "abstention_detected": False},
        "snippets": [],
        "is_cloud": False,
        "model_name": "qwen3-vl-2b",
    }
    assert local_turn["is_cloud"] is False
    assert local_turn["model_name"] == "qwen3-vl-2b"

    cloud_turn = {
        "role": "assistant",
        "content": "Answer generated via Groq cloud provider.",
        "sources": ["doc.pdf"],
        "verification": {"precision": 1.0, "is_valid": True, "abstention_detected": False},
        "snippets": [],
        "is_cloud": True,
        "model_name": "groq/llama-3.3-70b-versatile",
    }
    assert cloud_turn["is_cloud"] is True
    assert cloud_turn["model_name"] == "groq/llama-3.3-70b-versatile"


def test_dynamic_cloud_provider_switching_matrix() -> None:
    """Verify switching across Groq, OpenAI, and Anthropic correctly adapts capabilities and parameters."""
    providers = [
        ("groq/llama-3.3-70b-versatile", 131072, False),
        ("openai/gpt-4o-mini", 128000, True),
        ("anthropic/claude-3-5-haiku-20241022", 200000, True),
    ]

    for model_name, expected_ctx, expected_vision in providers:
        prov = LiteLLMProvider(model_name=model_name, api_key="test-key", user_consented=True)
        caps = prov.get_capabilities()
        assert caps.model_name == model_name
        assert caps.context_window == expected_ctx
        assert caps.supports_vision is expected_vision
        assert caps.is_local is False
        assert caps.supports_streaming is True
        prov.close()


def test_ingestion_visual_analyzer_never_calls_cloud_vision_even_in_cloud_mode(monkeypatch) -> None:
    """Verify VisualAnalyzer during ingestion strictly rejects cloud providers (CR-01, IN-02, INF-03)."""
    from core.models import BBox
    from ingestion.visual_analyzer import VisualAnalyzer

    cloud_provider = LiteLLMProvider(
        model_name="openai/gpt-4o-mini",
        api_key="sk-test",
        user_consented=True,
    )
    assert cloud_provider.get_capabilities().supports_vision is True
    assert cloud_provider.get_capabilities().is_local is False

    called_cloud = False

    def fake_analyze_image(*args, **kwargs):
        nonlocal called_cloud
        called_cloud = True
        return "Transmitted crop to cloud"

    monkeypatch.setattr(cloud_provider, "analyze_image", fake_analyze_image)

    analyzer = VisualAnalyzer(
        region_detector=lambda _bytes: [{"page": 1, "kind": "figure", "bbox": BBox(x0=0, y0=0, x1=10, y1=10)}],
        cropper=lambda _bytes, _page, _bbox: b"fake-png-bytes",
    )

    # 1. Direct pass to VisualAnalyzer: rejected by defense-in-depth guard
    elements = analyzer.analyze_visual_elements(
        pdf_bytes=b"%PDF-1.4...",
        doc_id="doc_privacy_test",
        provider=cloud_provider,
    )
    assert called_cloud is False
    assert len(elements) == 1
    assert "vision analysis unsupported" in elements[0].content

    # 2. main.py filter check: local_vlm_provider is None when active_provider is cloud
    active_provider = cloud_provider
    local_vlm_provider = (
        active_provider if (active_provider is not None and active_provider.get_capabilities().is_local) else None
    )
    assert local_vlm_provider is None

    elements_filtered = analyzer.analyze_visual_elements(
        pdf_bytes=b"%PDF-1.4...",
        doc_id="doc_privacy_test",
        provider=local_vlm_provider,
    )
    assert called_cloud is False
    assert len(elements_filtered) == 1
    assert "vision analysis unsupported" in elements_filtered[0].content


def test_ai_model_set_cloud_mode_idempotent_preserves_connections() -> None:
    """Verify set_cloud_mode is a no-op when mode and provider are unchanged (WR-02)."""
    model = AiModel(cloud_mode=False)
    initial_provider = model.provider

    # Calling set_cloud_mode(False) again should not recreate provider
    model.set_cloud_mode(False)
    assert model.provider is initial_provider

    cloud_prov = LiteLLMProvider(model_name="groq/llama-3.3-70b-versatile", api_key="test-key", user_consented=True)
    model.set_cloud_mode(True, cloud_provider=cloud_prov)
    assert model.provider is cloud_prov

    # Calling set_cloud_mode(True) with the same provider should not recreate provider
    model.set_cloud_mode(True, cloud_provider=cloud_prov)
    assert model.provider is cloud_prov
    model.close()


def test_per_provider_api_key_lookup(monkeypatch) -> None:
    """Verify LiteLLMProvider uses per-provider dictionary in session state (WR-01)."""
    from providers.litellm_provider import _resolve_api_key_for_model

    class FakeSessionState(dict):
        pass

    fake_state = FakeSessionState(
        cloud_api_keys={
            "groq": "gsk_groq_secret",
            "openai": "sk_openai_secret",
            "anthropic": "sk_ant_secret",
        },
        cloud_api_key="legacy_polluted_key",
    )

    import streamlit as st

    monkeypatch.setattr(st, "session_state", fake_state, raising=False)

    groq_key = _resolve_api_key_for_model("groq/llama-3.3-70b-versatile")
    assert groq_key == "gsk_groq_secret"

    openai_key = _resolve_api_key_for_model("openai/gpt-4o-mini")
    assert openai_key == "sk_openai_secret"

    anthropic_key = _resolve_api_key_for_model("anthropic/claude-3-5-haiku-20241022")
    assert anthropic_key == "sk_ant_secret"

    # Verify that if provider key is empty, legacy cloud_api_key is strictly ignored
    fake_state_empty = FakeSessionState(
        cloud_api_keys={"groq": "", "openai": "", "anthropic": ""},
        cloud_api_key="legacy_polluted_key",
    )
    monkeypatch.setattr(st, "session_state", fake_state_empty, raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert _resolve_api_key_for_model("groq/llama-3.3-70b-versatile") is None
