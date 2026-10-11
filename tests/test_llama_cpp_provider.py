"""Offline unit tests for LlamaCppProvider using httpx.MockTransport."""

import base64
import json
import httpx
import pytest

from llama_cpp_provider import LlamaCppProvider


def test_capabilities() -> None:
    """Test get_capabilities returns expected local VLM specifications."""
    provider = LlamaCppProvider(
        base_url="http://127.0.0.1:8080",
        model_name="qwen3-vl-2b",
        context_window=4096,
    )
    caps = provider.get_capabilities()
    assert caps.model_name == "qwen3-vl-2b"
    assert caps.context_window == 4096
    assert caps.supports_vision is True
    assert caps.is_local is True
    assert caps.supports_streaming is True
    provider.close()


def test_health_check_healthy() -> None:
    """Test check_health when llama-server responds 200 OK."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    status = provider.check_health()
    assert status.status == "healthy"
    assert "ready" in status.message.lower() or "active" in status.message.lower()
    assert status.latency_ms >= 0.0
    provider.close()


def test_health_check_loading_503() -> None:
    """Test check_health when llama-server returns 503 while loading model weights."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        return httpx.Response(503, json={"status": "loading model"})

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    status = provider.check_health()
    assert status.status == "loading"
    assert "loading" in status.message.lower()
    provider.close()


def test_health_check_unreachable() -> None:
    """Test check_health when connection is refused / unreachable."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    status = provider.check_health()
    assert status.status == "unreachable"
    assert "llama-server" in status.message
    assert "-m models/" in status.message
    provider.close()


def test_health_check_error_status() -> None:
    """Test check_health when llama-server returns unexpected 500 error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    status = provider.check_health()
    assert status.status == "error"
    assert "500" in status.message
    provider.close()


def test_generate_text_success() -> None:
    """Test generate_text synchronous completion."""
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        assert request.url.path == "/v1/chat/completions"
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Generated reply."}}]},
        )

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    result = provider.generate_text(
        prompt="Explain quantum physics",
        system_prompt="You are a physics professor.",
        max_tokens=256,
        temperature=0.3,
    )
    assert result == "Generated reply."
    assert captured_payload["model"] == "qwen3-vl-2b"
    assert captured_payload["max_tokens"] == 256
    assert captured_payload["temperature"] == 0.3
    assert captured_payload["stream"] is False
    assert captured_payload["messages"] == [
        {"role": "system", "content": "You are a physics professor."},
        {"role": "user", "content": "Explain quantum physics"},
    ]
    provider.close()


def test_generate_text_http_error() -> None:
    """Test generate_text raises RuntimeError on HTTP failure."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="CUDA out of memory")

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    with pytest.raises(RuntimeError, match="llama-server generation failed"):
        provider.generate_text("test")
    provider.close()


def test_stream_text_multi_chunk() -> None:
    """Test stream_text correctly parses multi-chunk SSE stream and terminates on [DONE]."""
    captured_payload: dict = {}

    sse_body = (
        b": keepalive\n\n"
        b'data: {"choices": [{"delta": {"content": "The "}}]}\n\n'
        b'data: {"choices": [{"delta": {"content": "quick "}}]}\n\n'
        b'data: {"choices": [{"delta": {"content": "brown fox."}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        assert request.url.path == "/v1/chat/completions"
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body,
        )

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    tokens = list(
        provider.stream_text(
            prompt="tell me a story",
            system_prompt="system guide",
            history=history,
            max_tokens=500,
        )
    )

    assert tokens == ["The ", "quick ", "brown fox."]
    assert captured_payload["stream"] is True
    assert captured_payload["messages"] == [
        {"role": "system", "content": "system guide"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "tell me a story"},
    ]
    provider.close()


def test_stream_text_error() -> None:
    """Test stream_text raises RuntimeError on HTTP error response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Invalid request")

    transport = httpx.MockTransport(handler)
    provider = LlamaCppProvider(transport=transport)
    with pytest.raises(RuntimeError, match="llama-server streaming failed"):
        list(provider.stream_text("hello"))
    provider.close()


def test_analyze_image_payload() -> None:
    """Test analyze_image formats base64 vision payload accurately."""
    captured_payload: dict = {}
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        assert request.url.path == "/v1/chat/completions"
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Chart shows 40% growth in Q3.",
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    with LlamaCppProvider(transport=transport) as provider:
        summary = provider.analyze_image(fake_png, "Describe the chart in detail.")
        assert summary == "Chart shows 40% growth in Q3."

    assert captured_payload["stream"] is False
    assert captured_payload["max_tokens"] == 512
    user_msg = captured_payload["messages"][0]
    assert user_msg["role"] == "user"
    contents = user_msg["content"]
    assert contents[0] == {"type": "text", "text": "Describe the chart in detail."}
    assert contents[1]["type"] == "image_url"
    expected_b64 = base64.b64encode(fake_png).decode("ascii")
    assert contents[1]["image_url"]["url"] == f"data:image/jpeg;base64,{expected_b64}"
