"""Integration tests for chat session CRUD and SSE message streaming."""

from unittest.mock import MagicMock
import pytest
from starlette.testclient import TestClient

from api.main import app
from api.deps import get_container


@pytest.fixture
def client_with_mock_container(tmp_path):
    from api.config import Settings
    from api.container import AppContainer

    s = Settings(data_dir=tmp_path / "data", cache_dir=tmp_path / ".cache")
    container = AppContainer.build(s)

    # Mock AI model response
    mock_ai = MagicMock()
    mock_provider = MagicMock()
    mock_caps = MagicMock()
    mock_caps.is_local = True
    mock_caps.context_window = 16384
    mock_provider.get_capabilities.return_value = mock_caps
    mock_ai.provider = mock_provider
    mock_ai.get_capabilities.return_value = mock_caps

    def fake_stream(*args, **kwargs):
        yield "Hello"
        yield " world"

    mock_ai.ask_a_question_from_pdf_stream.side_effect = fake_stream
    container.ai_model = mock_ai

    app.dependency_overrides[get_container] = lambda: container
    client = TestClient(app, base_url="http://127.0.0.1")
    yield client
    app.dependency_overrides.clear()
    container.shutdown()


def test_chat_session_lifecycle(client_with_mock_container):
    client = client_with_mock_container

    # 1. Create chat session
    res = client.post(
        "/api/v1/chat/sessions",
        headers={"x-rag-client": "web"},
        json={"title": "Test Session", "scope": {"type": "all", "doc_ids": []}},
    )
    assert res.status_code == 200, res.text
    session_data = res.json()
    session_id = session_data["id"]
    assert session_data["title"] == "Test Session"

    # 2. List sessions
    res = client.get("/api/v1/chat/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert any(s["id"] == session_id for s in sessions)

    # 3. Stream a chat message over SSE
    with client.stream(
        "POST",
        f"/api/v1/chat/sessions/{session_id}/messages/stream",
        headers={"x-rag-client": "web"},
        json={"content": "What is in the document?", "scope": {"type": "all", "doc_ids": []}},
    ) as stream_resp:
        assert stream_resp.status_code == 200
        assert "text/event-stream" in stream_resp.headers["content-type"]
        body = "".join(chunk for chunk in stream_resp.iter_text())
        assert "event: token" in body or "event: final" in body or "event: phase" in body

    # 4. Delete session
    res = client.delete(
        f"/api/v1/chat/sessions/{session_id}",
        headers={"x-rag-client": "web"},
    )
    assert res.status_code == 200
    assert res.json() == {"deleted": True}
