"""Local inference provider for llama-server (llama.cpp) supporting Qwen3-VL 2B GGUF.

Communicates with llama-server over local HTTP REST endpoints, offering
text generation, incremental SSE streaming, multimodal image analysis,
and health diagnostics without any outbound network calls.
"""

import base64
from collections.abc import Generator
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.parse import urlparse

import httpx

from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities


class LlamaCppProvider(BaseModelProvider):
    """Client for local llama-server implementing the BaseModelProvider interface."""

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str = "qwen3-vl-2b",
        context_window: int = 4096,
        transport: httpx.BaseTransport | None = None,
        allow_remote: bool = False,
    ) -> None:
        """Initialize the local llama.cpp provider.

        Args:
            base_url: Base URL of the llama-server instance.
            model_name: Identifier for the model.
            context_window: Bounded context token capacity (default 4096).
            transport: Optional custom HTTP transport (e.g. httpx.MockTransport for tests).
            allow_remote: Whether to allow non-loopback endpoints (default False).
        """
        if base_url is None:
            env_url = os.environ.get("LLAMA_SERVER_URL")
            if env_url:
                base_url = env_url
            else:
                env_host = os.environ.get("LLAMA_SERVER_HOST")
                env_port = os.environ.get("LLAMA_SERVER_PORT", "8080")
                if env_host:
                    base_url = f"http://{env_host}:{env_port}"
                else:
                    base_url = "http://127.0.0.1:8080"

        url_to_parse = base_url if "://" in base_url else f"http://{base_url}"
        parsed = urlparse(url_to_parse)
        host = (parsed.hostname or "").lower()

        # Local loopback & container networking endpoints (e.g. Docker bridge to host)
        local_hostnames = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "llama-server"}
        is_loopback = host in local_hostnames
        if not is_loopback and host:
            try:
                is_loopback = ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_loopback = False

        if not allow_remote and not is_loopback:
            raise ValueError(
                f"Restricted endpoint: '{base_url}' (host '{host}') is not a local loopback address. "
                "Specify a loopback URL or pass allow_remote=True."
            )

        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.context_window = context_window
        self.allow_remote = allow_remote
        self._client = httpx.Client(
            base_url=self.base_url,
            transport=transport,
            timeout=httpx.Timeout(connect=2.0, read=60.0, write=10.0, pool=5.0),
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def check_health(self) -> HealthStatus:
        """Check whether llama-server is healthy, loading, or unreachable.

        Returns:
            HealthStatus schema with connectivity state and diagnostics.
        """
        start = time.perf_counter()
        try:
            resp = self._client.get("/health", timeout=2.0)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

            if resp.status_code == 200:
                return HealthStatus(
                    status="healthy",
                    message="llama-server is active and ready.",
                    latency_ms=elapsed_ms,
                )
            if resp.status_code == 503:
                return HealthStatus(
                    status="loading",
                    message="llama-server is loading the model into VRAM. Please wait...",
                    latency_ms=elapsed_ms,
                )
            return HealthStatus(
                status="error",
                message=f"llama-server returned unexpected status code: {resp.status_code}",
                latency_ms=elapsed_ms,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout):
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            local_bin = (
                Path(__file__).resolve().parent
                / "tools"
                / "llama-server"
                / ("llama-server.exe" if sys.platform == "win32" else "llama-server")
            )
            bin_cmd = str(local_bin) if local_bin.exists() and not shutil.which("llama-server") else "llama-server"
            setup_cmd = (
                f"{bin_cmd} -m models/{self.model_name}-instruct-q4_k_m.gguf "
                f"--mmproj models/mmproj-f16.gguf -c {self.context_window} -ngl 28 --port 8080"
            )
            return HealthStatus(
                status="unreachable",
                message=(f"Cannot connect to llama-server at {self.base_url}. Start it with:\n{setup_cmd}"),
                latency_ms=elapsed_ms,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            return HealthStatus(
                status="error",
                message=f"llama-server health check error: {exc}",
                latency_ms=elapsed_ms,
            )

    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect provider capabilities.

        Returns:
            ProviderCapabilities for local Qwen3-VL 2B.
        """
        return ProviderCapabilities(
            model_name=self.model_name,
            context_window=self.context_window,
            supports_vision=True,
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
        """Generate a complete text response synchronously from llama-server.

        Args:
            prompt: User prompt or grounded instruction.
            system_prompt: Optional system prompt instructions.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.

        Returns:
            Extracted text content from the response.

        Raises:
            RuntimeError: If the server returns an HTTP error or invalid response.
        """
        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": clamped_temp,
            "stream": False,
        }

        try:
            resp = self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"])
        except httpx.HTTPError as exc:
            raise RuntimeError(f"llama-server generation failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"llama-server returned malformed response payload: {exc}") from exc

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Generator[str, None, None]:
        """Stream response tokens from llama-server via Server-Sent Events (SSE).

        Args:
            prompt: Current turn prompt.
            system_prompt: Optional system instructions.
            history: Optional conversation history.
            max_tokens: Maximum generation tokens.
            temperature: Sampling temperature.

        Yields:
            Incremental text tokens.

        Raises:
            RuntimeError: If the stream fails or server returns an HTTP error.
        """
        clamped_temp = max(0.0, min(2.0, float(temperature)))
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": clamped_temp,
            "stream": True,
        }

        try:
            with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                for raw_line in resp.iter_lines():
                    line = raw_line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except (json.JSONDecodeError, IndexError, KeyError):
                            continue
        except httpx.HTTPError as exc:
            raise RuntimeError(f"llama-server streaming failed: {exc}") from exc

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        """Analyze an image using the multimodal capabilities of llama-server.

        Args:
            image_bytes: Raw bytes of image.
            prompt: Text prompt asking for image description or analysis.
            max_tokens: Maximum tokens in description.

        Returns:
            Description or visual analysis from the model.

        Raises:
            ValueError: If image_bytes is empty.
            RuntimeError: If analysis request fails.
        """
        if not image_bytes:
            raise ValueError("image_bytes cannot be empty.")

        b64_image = base64.b64encode(image_bytes).decode("ascii")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            }
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }

        try:
            resp = self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return str(data["choices"][0]["message"]["content"])
        except httpx.HTTPError as exc:
            raise RuntimeError(f"llama-server image analysis failed: {exc}") from exc
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"llama-server returned malformed image analysis payload: {exc}") from exc
