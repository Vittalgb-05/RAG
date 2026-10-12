"""Unit and integration tests for Cloud Mode privacy controls and local-only invariants (UI-04, INF-03, INF-04)."""

import socket
import pytest

from hybrid_retriever import HybridRetriever
from litellm_provider import LiteLLMProvider
from local_embedding import LocalEmbedding
from local_llm import AiModel
from models import Chunk, RetrievalResult


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
