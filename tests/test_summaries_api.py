"""Integration tests for document summarization endpoints and cache invalidation."""

from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.deps import get_container
from core.models import Document, SummaryResult
from core.summarizer import compute_summary_model_version


@pytest.fixture
def client_with_summary_container(tmp_path):
    from api.config import Settings
    from api.container import AppContainer

    s = Settings(data_dir=tmp_path / "data", cache_dir=tmp_path / ".cache")
    container = AppContainer.build(s)

    mock_ai = MagicMock()
    mock_caps = MagicMock()
    mock_caps.is_local = True
    mock_caps.model_name = "local"
    mock_ai.get_capabilities.return_value = mock_caps
    container.ai_model = mock_ai

    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app, base_url="http://127.0.0.1")
    yield client, container
    app.dependency_overrides.clear()
    container.shutdown()


def test_get_summary_not_found(client_with_summary_container):
    client, _ = client_with_summary_container
    res = client.get("/api/v1/summaries/doc_missing/overview")
    assert res.status_code == 404


def test_summary_cache_hit_and_clear(client_with_summary_container):
    client, container = client_with_summary_container

    doc = Document(
        doc_id="doc_summary_1",
        filename="paper.pdf",
        sha256="c" * 64,
        size_bytes=2048,
        num_pages=2,
        status="indexed",
        upload_time="2026-11-14T00:00:00Z",
        num_chunks=4,
    )
    container.doc_store.upsert_document(doc)

    model_ver = compute_summary_model_version("local", "standard")
    container.doc_store.save_summary(
        SummaryResult(
            summary_id="summ_test_01",
            doc_id=doc.doc_id,
            sha256=doc.sha256,
            profile="overview",
            summary_text="Precomputed executive summary.",
            created_at="2026-11-14T00:00:00Z",
            model_version=model_ver,
            cached=True,
        )
    )

    # 1. GET returns cached summary
    res = client.get(f"/api/v1/summaries/{doc.doc_id}/overview")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"] == "Precomputed executive summary."
    assert data["cached"] is True

    # 2. POST without force returns cached summary directly
    res = client.post(
        "/api/v1/summaries",
        headers={"x-rag-client": "web"},
        json={"doc_id": doc.doc_id, "profile": "overview", "length": "standard", "force": False},
    )
    assert res.status_code == 200
    assert res.json()["cached"] is True
    assert res.json()["summary"] == "Precomputed executive summary."

    # 3. DELETE clears cached summaries
    res = client.delete(
        f"/api/v1/summaries/{doc.doc_id}",
        headers={"x-rag-client": "web"},
    )
    assert res.status_code == 200
    assert res.json() == {"deleted": True}

    # 4. GET now returns 404
    res = client.get(f"/api/v1/summaries/{doc.doc_id}/overview")
    assert res.status_code == 404
