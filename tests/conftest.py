# ------------------------------------------------------------------
# Pytest Shared Fixtures & Mocking Seams
# Allows 100% offline unit testing without GPU allocation or API calls
# ------------------------------------------------------------------

import os

# Enforce PyTorch backend and suppress Keras 3 / TensorFlow integrations in tests
os.environ["USE_TF"] = "0"
os.environ["USE_TORCH"] = "1"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

from pathlib import Path
from unittest.mock import MagicMock
import numpy as np
import pytest


@pytest.fixture
def fake_env_groq_key(monkeypatch):
    """Sets a mock GROQ_API_KEY in the environment for tests."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-a-secret-mock-value")


@pytest.fixture
def mock_groq_client(monkeypatch):
    """Mocks the groq.Groq client and chat.completions.create streaming response.

    Yields canned delta.content chunks.
    """
    mock_client = MagicMock()

    class MockDelta:
        def __init__(self, content):
            self.content = content

    class MockChoice:
        def __init__(self, content):
            self.delta = MockDelta(content)

    class MockChunk:
        def __init__(self, content):
            self.choices = [MockChoice(content)]

    def mock_create(*args, **kwargs):
        # Generator returning mock token chunks
        for token in ["This ", "is ", "a ", "grounded ", "answer."]:
            yield MockChunk(token)

    mock_client.chat.completions.create.side_effect = mock_create

    try:
        import groq_provider

        monkeypatch.setattr(groq_provider, "Groq", lambda api_key=None: mock_client)
    except (ImportError, AttributeError):
        pass

    return mock_client


@pytest.fixture
def mock_sentence_transformer(monkeypatch):
    """
    Mocks SentenceTransformer in local_embedding.
    Returns deterministic 384-dimensional normalized float32 vectors.
    """
    mock_model = MagicMock()

    def mock_encode(texts, normalize_embeddings=True, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        # Create deterministic pseudo-embeddings based on text length
        vectors = []
        for i, t in enumerate(texts):
            vec = np.zeros(384, dtype=np.float32)
            # Use deterministic signal in first 3 dimensions
            vec[0] = 1.0 + (len(t) % 10) * 0.1
            vec[1] = 0.5 + (i % 5) * 0.1
            if normalize_embeddings:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    mock_model.encode.side_effect = mock_encode

    import local_embedding

    monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name, **kwargs: mock_model)
    return mock_model


@pytest.fixture
def sample_pdf_path():
    """Returns the path to the synthetic clean_digital.pdf."""
    path = Path(__file__).resolve().parent / "data" / "corpus" / "clean_digital.pdf"
    return str(path)


@pytest.fixture
def mock_llama_provider():
    """Provides a healthy mock local inference provider conforming to BaseModelProvider."""
    from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities

    class MockLlamaCppProvider(BaseModelProvider):
        def __init__(self, healthy=True, tokens=None):
            self._healthy = healthy
            self._tokens = tokens or ["This ", "is ", "a ", "grounded ", "answer."]
            self.stream_calls = []

        def check_health(self) -> HealthStatus:
            if self._healthy:
                return HealthStatus(
                    status="healthy",
                    message="Mock llama-server ready.",
                    latency_ms=1.5,
                )
            return HealthStatus(
                status="unreachable",
                message="Mock llama-server unreachable.\nStart it with:\nllama-server -m models/qwen3-vl-2b-instruct-q4_k_m.gguf",
                latency_ms=1.5,
            )

        def get_capabilities(self) -> ProviderCapabilities:
            return ProviderCapabilities(
                model_name="qwen3-vl-2b",
                context_window=4096,
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
            return "".join(self._tokens)

        def stream_text(
            self,
            prompt: str,
            system_prompt: str | None = None,
            history: list[dict[str, str]] | None = None,
            max_tokens: int = 1024,
            temperature: float = 0.2,
        ):
            self.stream_calls.append(
                {
                    "prompt": prompt,
                    "system_prompt": system_prompt,
                    "history": history,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            )
            for token in self._tokens:
                yield token

        def analyze_image(
            self,
            image_bytes: bytes,
            prompt: str,
            max_tokens: int = 512,
        ) -> str:
            return f"Mock visual analysis for: {prompt}"

    return MockLlamaCppProvider()
