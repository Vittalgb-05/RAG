"""AI Model interface delegating to BaseModelProvider implementations.

Provides unified streaming response generation, bounded context budgeting,
prompt injection isolation (<document_context>), and resilient fallback between
local llama-server (Qwen3-VL 2B GGUF) and cloud Groq inference.
"""

from collections.abc import Generator
from contextlib import contextmanager
import logging
import threading

from citation_validator import CitationVerificationResult, validate_citations
from groq_provider import GroqProvider
from hybrid_retriever import HybridRetriever
from llama_cpp_provider import LlamaCppProvider
from local_embedding import LocalEmbedding
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities
from models import RetrievalResult
from pdf_reader import PdfReader
from prompt_budget import assemble_grounded_messages

logger = logging.getLogger(__name__)


class InferenceGate:
    """Process-level reentrant lock guaranteeing max one active GPU inference operation.

    Enforces memory safety within the 4 GB VRAM envelope on RTX 3050 Laptop GPU (QUAL-01).
    Prevents concurrent token generation or summarization calls from colliding and causing
    out-of-memory crashes.
    """

    _lock = threading.RLock()
    _active_threads: int = 0
    _state_lock = threading.Lock()

    @classmethod
    def acquire(cls, timeout: float = 60.0) -> bool:
        """Acquire exclusive inference access with a timeout.

        Args:
            timeout: Maximum seconds to wait for lock acquisition.

        Returns:
            True if acquired, False on timeout.
        """
        acquired = cls._lock.acquire(timeout=timeout)
        if acquired:
            with cls._state_lock:
                cls._active_threads += 1
        return acquired

    @classmethod
    def release(cls) -> None:
        """Release previously acquired inference access."""
        try:
            with cls._state_lock:
                if cls._active_threads > 0:
                    cls._active_threads -= 1
            cls._lock.release()
        except RuntimeError:
            pass

    @classmethod
    def is_locked(cls) -> bool:
        """Check if the inference gate is currently held by any thread."""
        with cls._state_lock:
            return cls._active_threads > 0

    @classmethod
    @contextmanager
    def hold(cls, timeout: float = 60.0) -> Generator[None, None, None]:
        """Context manager to safely acquire and release the inference gate.

        Args:
            timeout: Maximum seconds to wait for gate acquisition.

        Raises:
            TimeoutError: If inference lock cannot be acquired within timeout.
        """
        acquired = cls.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"InferenceGate acquisition timed out after {timeout}s: another inference request is currently active."
            )
        try:
            yield
        finally:
            cls.release()


class AiModel:
    """Orchestrates document Q&A inference across local or cloud providers.

    Note:
        When instantiated as a server-level resource (e.g. via @st.cache_resource),
        AiModel acts as a process singleton. Callers should pass an explicit
        retrieval_result to validate_response(...) to prevent cross-session evidence
        contamination in multi-user deployments.
    """

    def __init__(self, provider: BaseModelProvider | None = None) -> None:
        """Initialize AiModel with an explicit provider or auto-detected default.

        Args:
            provider: Optional explicit BaseModelProvider. If omitted, probes
                     local llama-server first; falls back to Groq if key is present;
                     defaults to local provider with diagnostic state if neither is ready.
        """
        if provider is not None:
            self.provider = provider
        else:
            self.provider = self._detect_provider()

        self.model_name = self.provider.get_capabilities().model_name
        self.last_retrieval_result: RetrievalResult | None = None
        self.last_verification_result: CitationVerificationResult | None = None

    def close(self) -> None:
        """Close underlying provider resources."""
        if hasattr(self.provider, "close"):
            self.provider.close()

    def __enter__(self) -> "AiModel":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _detect_provider(self) -> BaseModelProvider:
        """Probe local llama-server and cloud Groq to choose the active provider.

        Returns:
            The selected BaseModelProvider instance.
        """
        # 1. Probe local llama-server
        local = LlamaCppProvider()
        health = local.check_health()
        if health.status == "healthy":
            return local

        # 2. Probe Groq Cloud fallback
        groq_provider = GroqProvider()
        groq_health = groq_provider.check_health()
        if groq_health.status == "healthy":
            local.close()
            return groq_provider

        # 3. Default to local provider so health checks display actionable setup guidance
        groq_provider.close()
        return local

    def check_health(self) -> HealthStatus:
        """Check operational status of the active provider, re-probing if unhealthy.

        Returns:
            HealthStatus schema from active provider.
        """
        current_status = self.provider.check_health()
        if current_status.status != "healthy":
            # Re-probe providers dynamically to recover if llama-server was started
            # or Groq credentials were added after initial startup
            new_provider = self._detect_provider()
            new_status = new_provider.check_health()
            if new_status.status == "healthy":
                self.close()
                self.provider = new_provider
                self.model_name = new_provider.get_capabilities().model_name
                return new_status
            else:
                new_provider.close()

        return current_status

    def get_capabilities(self) -> ProviderCapabilities:
        """Inspect capabilities of the active provider.

        Returns:
            ProviderCapabilities schema.
        """
        return self.provider.get_capabilities()

    def ask_a_question_from_pdf_stream(
        self,
        pdf_path: str = "",
        prompt: str = "tell me what is this pdf about",
        local_embedding: LocalEmbedding | HybridRetriever | None = None,
        chat_history: list[dict[str, str]] | None = None,
        retrieval_result: RetrievalResult | None = None,
    ) -> Generator[str, None, None]:
        """Stream answer tokens grounded in retrieved document context.

        Args:
            pdf_path: Path to PDF if building embedding on-the-fly.
            prompt: User question.
            local_embedding: Existing vector index or hybrid retriever instance.
            chat_history: Prior conversation turns.
            retrieval_result: Optional pre-computed canonical RetrievalResult (RETR-04).

        Yields:
            Token text chunks as generated.
        """
        if retrieval_result is not None:
            relevant_sections = retrieval_result.formatted_evidence()
        else:
            if local_embedding is None and pdf_path:
                pdf_reader = PdfReader(pdf_path)
                pdf_paragraphs = pdf_reader.get_paragraphs()
                local_embedding = LocalEmbedding()
                local_embedding.build_index(pdf_paragraphs)

            # Contextualize search query with previous user question if history exists
            search_query = prompt
            if chat_history:
                last_user_msgs = [
                    m["content"]
                    for m in chat_history
                    if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str)
                ]
                if last_user_msgs:
                    search_query = f"{last_user_msgs[-1]} {prompt}"

            if local_embedding:
                if isinstance(local_embedding, HybridRetriever):
                    retrieval_result = local_embedding.search_hybrid(search_query, k=10)
                    relevant_sections = retrieval_result.formatted_evidence()
                elif hasattr(local_embedding, "get_context"):
                    relevant_sections = local_embedding.get_context(search_query, k=10)
                    if hasattr(local_embedding, "last_retrieval_result"):
                        retrieval_result = getattr(local_embedding, "last_retrieval_result")
                elif hasattr(local_embedding, "search_hybrid"):
                    retrieval_result = local_embedding.search_hybrid(search_query, k=10)
                    relevant_sections = (
                        retrieval_result.formatted_evidence()
                        if hasattr(retrieval_result, "formatted_evidence")
                        else str(retrieval_result)
                    )
                else:
                    relevant_sections = ""
            else:
                relevant_sections = ""

        self.last_retrieval_result = retrieval_result

        caps = self.provider.get_capabilities()
        messages = assemble_grounded_messages(
            prompt=prompt,
            context_text=relevant_sections,
            history=chat_history,
            max_context_tokens=caps.context_window,
        )

        system_prompt = messages[0]["content"]
        history_turns = messages[1:-1]
        bounded_prompt = messages[-1]["content"]

        acquired = InferenceGate.acquire(timeout=60.0)
        if not acquired:
            yield "⚠️ System is busy processing another inference request. Please retry in a moment."
            return

        try:
            yield from self.provider.stream_text(
                prompt=bounded_prompt,
                system_prompt=system_prompt,
                history=history_turns,
                max_tokens=1024,
            )
        finally:
            InferenceGate.release()

    def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 60.0,
    ) -> str:
        """Execute non-streaming text generation guarded by InferenceGate.

        Args:
            prompt: User prompt.
            system_prompt: Optional system instruction.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            timeout: Timeout in seconds for acquiring InferenceGate.

        Returns:
            Generated text string.
        """
        with InferenceGate.hold(timeout=timeout):
            return self.provider.generate_text(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    def validate_response(
        self,
        response_text: str,
        retrieval_result: RetrievalResult | None = None,
    ) -> CitationVerificationResult:
        """Validate citations in generated response against active or provided evidence.

        Args:
            response_text: Completed assistant response text.
            retrieval_result: Optional override for retrieval result. If None, uses
                              last_retrieval_result from previous inference call.

        Returns:
            CitationVerificationResult schema.
        """
        active_result = retrieval_result if retrieval_result is not None else self.last_retrieval_result
        verification = validate_citations(response_text, active_result)
        self.last_verification_result = verification
        return verification
