"""Offline unit tests for LlamaCppProvider using httpx.MockTransport."""

import base64
import json
import httpx
import pytest

from providers.llama_cpp_provider import LlamaCppProvider


def test_capabilities() -> None:
    """Test get_capabilities returns expected local VLM specifications."""
    provider = LlamaCppProvider(
        base_url="http://127.0.0.1:8080",
        model_name="qwen3.5-2b",
        context_window=4096,
    )
    caps = provider.get_capabilities()
    assert caps.model_name == "qwen3.5-2b"
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
    assert captured_payload["model"] == "qwen3.5-2b"
    assert captured_payload["max_tokens"] == 256
    assert captured_payload["temperature"] == 0.3
    assert captured_payload["stream"] is False
    # Qwen3.5 reasons by default, which would spend the grounded answer budget on
    # hidden reasoning tokens; every local request must opt out explicitly.
    assert captured_payload["reasoning_effort"] == "none"
    assert captured_payload["chat_template_kwargs"] == {"enable_thinking": False}
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
    assert contents[1]["image_url"]["url"] == f"data:image/png;base64,{expected_b64}"


def test_analyze_image_jpeg_mime_detected() -> None:
    """Regression: JPEG magic bytes must produce a data:image/jpeg URL."""
    captured_payload: dict = {}
    fake_jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    with LlamaCppProvider(transport=transport) as provider:
        provider.analyze_image(fake_jpeg, "Describe")

    expected_b64 = base64.b64encode(fake_jpeg).decode("ascii")
    assert captured_payload["messages"][0]["content"][1]["image_url"]["url"] == (
        f"data:image/jpeg;base64,{expected_b64}"
    )


def test_analyze_image_unsupported_format_warns_and_falls_back(caplog) -> None:
    """Unsupported image formats are logged at warning level and keep a JPEG fallback."""
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    with LlamaCppProvider(transport=transport) as provider, caplog.at_level("WARNING"):
        provider.analyze_image(b"not-an-image", "Describe")

    assert "Unsupported or undecodable image format" in caplog.text
    assert captured_payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_detect_image_mime_magic_bytes() -> None:
    from providers.llama_cpp_provider import detect_image_mime

    assert detect_image_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert detect_image_mime(b"\xff\xd8\xffrest") == "image/jpeg"
    assert detect_image_mime(b"GIF89a...") == "image/gif"
    assert detect_image_mime(b"RIFF\x00\x00\x00\x00WEBP...") == "image/webp"
    assert detect_image_mime(b"unknown") is None


def test_analyze_image_empty_bytes_raises() -> None:
    """Test analyze_image raises ValueError when given empty image bytes."""
    provider = LlamaCppProvider()
    with pytest.raises(ValueError, match="image_bytes cannot be empty"):
        provider.analyze_image(b"", "Describe image")
    provider.close()


def test_temperature_clamping() -> None:
    """Test temperature is clamped between 0.0 and 2.0."""
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.read())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    transport = httpx.MockTransport(handler)
    with LlamaCppProvider(transport=transport) as provider:
        provider.generate_text("test", temperature=5.0)
        assert captured_payload["temperature"] == 2.0

        provider.generate_text("test", temperature=-1.0)
        assert captured_payload["temperature"] == 0.0


def test_endpoint_loopback_validation_rejected() -> None:
    """Test non-loopback endpoints are rejected to prevent SSRF (SEC-01)."""
    with pytest.raises(ValueError, match="Restricted endpoint"):
        LlamaCppProvider(base_url="http://192.168.1.100:8080")

    with pytest.raises(ValueError, match="Restricted endpoint"):
        LlamaCppProvider(base_url="http://internal.corp.network:8080")


def test_endpoint_loopback_validation_allowed_with_flag() -> None:
    """Test non-loopback endpoints are allowed when allow_remote=True."""
    provider = LlamaCppProvider(base_url="http://192.168.1.100:8080", allow_remote=True)
    assert provider.base_url == "http://192.168.1.100:8080"
    assert provider.allow_remote is True
    provider.close()


def test_endpoint_loopback_accepted_addresses() -> None:
    """Test standard local loopback addresses are accepted by default."""
    accepted = [
        "http://127.0.0.1:8080",
        "http://localhost:8080",
        "http://[::1]:8080",
        "http://127.0.1.1:8080",
        "http://127.0.0.2:8080",
        "127.0.0.1:8080",
    ]
    for url in accepted:
        provider = LlamaCppProvider(base_url=url)
        assert provider.base_url == url.rstrip("/")
        provider.close()


def test_endpoint_docker_hostnames_accepted() -> None:
    """Test Docker internal hostnames are accepted for containerized deployments."""
    for url in ["http://host.docker.internal:8080", "http://llama-server:8080"]:
        provider = LlamaCppProvider(base_url=url)
        assert provider.base_url == url
        provider.close()


def test_endpoint_env_vars_consumed(monkeypatch) -> None:
    """Test LLAMA_SERVER_HOST and LLAMA_SERVER_PORT are consumed when base_url is omitted."""
    monkeypatch.setenv("LLAMA_SERVER_HOST", "host.docker.internal")
    monkeypatch.setenv("LLAMA_SERVER_PORT", "9090")
    provider = LlamaCppProvider()
    assert provider.base_url == "http://host.docker.internal:9090"
    provider.close()
