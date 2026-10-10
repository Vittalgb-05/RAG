# ------------------------------------------------------------------
# Pytest Shared Fixtures & Mocking Seams
# Allows 100% offline unit testing without GPU allocation or API calls
# ------------------------------------------------------------------

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
    """
    Mocks the groq.Groq client and chat.completions.create streaming response.
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

    import local_llm

    monkeypatch.setattr(local_llm, "Groq", lambda api_key=None: mock_client)
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

    monkeypatch.setattr(local_embedding, "SentenceTransformer", lambda model_name: mock_model)
    return mock_model


@pytest.fixture
def sample_pdf_path():
    """Returns the path to the synthetic clean_digital.pdf."""
    path = Path(__file__).resolve().parent / "data" / "corpus" / "clean_digital.pdf"
    return str(path)
