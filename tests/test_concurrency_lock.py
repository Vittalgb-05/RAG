"""Unit tests for InferenceGate process-level concurrency lock (QUAL-01)."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from local_llm import AiModel, InferenceGate
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities


class DummyProvider(BaseModelProvider):
    """Dummy provider for testing inference lock behavior."""

    def __init__(self) -> None:
        self.call_count = 0

    def check_health(self) -> HealthStatus:
        return HealthStatus(status="healthy", message="ok", provider_type="local")

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            model_name="dummy-model",
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
        self.call_count += 1
        time.sleep(0.01)
        return f"generated response for: {prompt}"

    def stream_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history: list[dict[str, str]] | None = None,
        max_tokens: int = 1024,
    ):
        yield "token1 "
        yield "token2"

    def analyze_image(
        self,
        image_bytes: bytes,
        prompt: str,
        max_tokens: int = 512,
    ) -> str:
        return "image analysis"


@pytest.fixture(autouse=True)
def ensure_gate_released() -> None:
    """Ensure InferenceGate is fully released before and after every test."""
    while InferenceGate.is_locked():
        InferenceGate.release()
    yield
    while InferenceGate.is_locked():
        InferenceGate.release()


def test_inference_gate_basic_acquire_release() -> None:
    """Test standard single-thread acquire and release."""
    assert not InferenceGate.is_locked()
    acquired = InferenceGate.acquire(timeout=1.0)
    assert acquired is True
    assert InferenceGate.is_locked()
    InferenceGate.release()
    assert not InferenceGate.is_locked()


def test_inference_gate_reentrancy_in_same_thread() -> None:
    """Test reentrancy: same thread can acquire multiple times without deadlocking."""
    with InferenceGate.hold(timeout=1.0):
        assert InferenceGate.is_locked()
        with InferenceGate.hold(timeout=1.0):
            assert InferenceGate.is_locked()
        assert InferenceGate.is_locked()
    assert not InferenceGate.is_locked()


def test_inference_gate_blocks_parallel_threads() -> None:
    """Test that second thread is blocked when first thread holds gate."""
    acquired_by_t2: list[bool] = []
    t1_started = threading.Event()
    t1_finish = threading.Event()

    def t1_worker() -> None:
        with InferenceGate.hold(timeout=2.0):
            t1_started.set()
            t1_finish.wait(timeout=2.0)

    def t2_worker() -> None:
        t1_started.wait(timeout=2.0)
        # Attempt to acquire with very short timeout while t1 holds it
        acquired = InferenceGate.acquire(timeout=0.05)
        acquired_by_t2.append(acquired)

    t1 = threading.Thread(target=t1_worker)
    t2 = threading.Thread(target=t2_worker)

    t1.start()
    t2.start()

    t2.join(timeout=3.0)
    t1_finish.set()
    t1.join(timeout=3.0)

    assert acquired_by_t2 == [False], "Thread 2 should have timed out while Thread 1 held the gate"
    assert not InferenceGate.is_locked()


def test_inference_gate_hold_raises_timeout_error() -> None:
    """Test InferenceGate.hold raises TimeoutError when lock is unavailable."""
    gate_held = threading.Event()
    release_gate = threading.Event()

    def lock_holder() -> None:
        with InferenceGate.hold(timeout=2.0):
            gate_held.set()
            release_gate.wait(timeout=2.0)

    t = threading.Thread(target=lock_holder)
    t.start()
    gate_held.wait(timeout=2.0)

    with pytest.raises(TimeoutError, match="InferenceGate acquisition timed out"):
        with InferenceGate.hold(timeout=0.05):
            pass

    release_gate.set()
    t.join(timeout=3.0)
    assert not InferenceGate.is_locked()


def test_ai_model_generate_text_guarded() -> None:
    """Test AiModel.generate_text executes while holding InferenceGate."""
    provider = DummyProvider()
    model = AiModel(provider=provider)

    gate_was_locked: list[bool] = []

    # Patch provider.generate_text to inspect lock state during invocation
    orig_generate = provider.generate_text

    def spy_generate(*args: object, **kwargs: object) -> str:
        gate_was_locked.append(InferenceGate.is_locked())
        return orig_generate(*args, **kwargs)

    provider.generate_text = spy_generate  # type: ignore[method-assign]

    response = model.generate_text("test query", max_tokens=100)
    assert "generated response" in response
    assert gate_was_locked == [True], "InferenceGate must be locked during generation"
    assert not InferenceGate.is_locked(), "InferenceGate must be released after generation"


def test_ai_model_streaming_busy_yields_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test ask_a_question_from_pdf_stream yields busy warning when gate cannot be acquired."""
    provider = DummyProvider()
    model = AiModel(provider=provider)

    monkeypatch.setattr(InferenceGate, "acquire", MagicMock(return_value=False))
    tokens = list(model.ask_a_question_from_pdf_stream(prompt="hello"))
    assert len(tokens) == 1
    assert "System is busy processing another inference request" in tokens[0]


def test_summarizer_guarded_by_inference_gate() -> None:
    """Test Summarizer.summarize_document executes with InferenceGate locked."""
    from models import Page
    from summarizer import Summarizer

    provider = DummyProvider()
    summarizer = Summarizer(provider=provider)

    gate_was_locked: list[bool] = []
    orig_generate = provider.generate_text

    def spy_generate(*args: object, **kwargs: object) -> str:
        gate_was_locked.append(InferenceGate.is_locked())
        return orig_generate(*args, **kwargs)

    provider.generate_text = spy_generate  # type: ignore[method-assign]

    pages = [
        Page(doc_id="doc_test", page_num=1, status="ok", char_count=50, num_chunks=1, page_text="Sample text (p. 1)")
    ]
    result = summarizer.summarize_document(doc_id="doc_test", sha256="a" * 64, pages=pages, profile="overview")

    assert result is not None
    assert gate_was_locked == [True]
    assert not InferenceGate.is_locked()
