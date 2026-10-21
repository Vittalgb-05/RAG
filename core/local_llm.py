"""AI Model interface delegating to BaseModelProvider implementations.

Provides unified streaming response generation, bounded context budgeting,
prompt injection isolation (<document_context>), and resilient fallback between
local llama-server (Qwen2-VL 2B GGUF) and cloud Groq inference.
"""

from collections.abc import Generator
from contextlib import contextmanager
import logging
import threading
import warnings

from core.citation_validator import CitationVerificationResult, validate_citations
from core.query_intent import contextualize_query, resolve_retrieval, whole_document_char_budget
from retrieval.hybrid_retriever import HybridRetriever
from providers.llama_cpp_provider import LlamaCppProvider
from retrieval.local_embedding import LocalEmbedding
from providers.model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities
from core.models import RetrievalResult
from core.prompt_budget import assemble_grounded_messages

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
        """Release previously acquired inference access.

        A foreign thread cannot release an ``RLock`` it does not own.  That case
        is logged rather than silently ignored, and the active counter is left
        untouched because the owning thread still holds the gate.
        """
        try:
            cls._lock.release()
        except RuntimeError:
            logger.warning(
                "InferenceGate.release() ignored: thread %s does not own the gate.",
                threading.get_ident(),
            )
            return

        with cls._state_lock:
            if cls._active_threads > 0:
                cls._active_threads -= 1

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
        In the application, AiModel is instantiated per session in st.session_state
        (via get_session_ai_model) to isolate user consent, active cloud credentials,
        and model routing across users (P1 audit). Callers should pass an explicit
        retrieval_result to validate_response(...) to prevent cross-turn evidence
        contamination.
    """

    def __init__(
        self,
        provider: BaseModelProvider | None = None,
        cloud_mode: bool = False,
        cloud_provider: BaseModelProvider | None = None,
    ) -> None:
        """Initialize AiModel with an explicit provider or auto-detected default.

        Args:
            provider: Optional explicit BaseModelProvider.
            cloud_mode: If True, activates consented cloud inference routing.
                        If False (default), stays strictly offline on local LlamaCppProvider (INF-03, INF-04).
            cloud_provider: Optional consented cloud provider instance (e.g. LiteLLMProvider).
        """
        self.cloud_mode = bool(cloud_mode)
        self.cloud_provider = cloud_provider

        if self.cloud_mode:
            active_cloud = cloud_provider if cloud_provider is not None else provider
            if active_cloud is None or not getattr(active_cloud, "user_consented", False):
                raise PermissionError(
                    "Cloud mode requires an explicitly consented cloud provider "
                    "(user_consented=True). Refusing to route document content externally."
                )

        if provider is not None:
            self.provider = provider
        else:
            self.provider = self._detect_provider()

        self.model_name = self.provider.get_capabilities().model_name
        self.last_retrieval_result: RetrievalResult | None = None
        self.last_verification_result: CitationVerificationResult | None = None
        self.last_truncation_warning: dict[str, bool] = {
            "prompt_truncated": False,
            "context_truncated": False,
            "history_truncated": False,
        }

    def close(self) -> None:
        """Close underlying provider resources."""
        if hasattr(self.provider, "close"):
            self.provider.close()

    def reset_turn_state(self) -> None:
        """Clear per-turn retrieval, citation, and truncation state.

        Called when the UI resets the session so the next question cannot reuse
        evidence or verification results from the previous conversation.
        """
        self.last_retrieval_result = None
        self.last_verification_result = None
        self.last_truncation_warning = {
            "prompt_truncated": False,
            "context_truncated": False,
            "history_truncated": False,
        }

    def __enter__(self) -> "AiModel":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def set_cloud_mode(self, enabled: bool, cloud_provider: BaseModelProvider | None = None) -> None:
        """Toggle between Local and Cloud inference modes dynamically.

        Args:
            enabled: True to activate Cloud Mode, False to force strictly local operation.
            cloud_provider: Optional consented cloud provider instance (e.g. LiteLLMProvider).
        """
        target_mode = bool(enabled)
        if target_mode:
            active_cloud = cloud_provider if cloud_provider is not None else self.cloud_provider
            if active_cloud is None or not getattr(active_cloud, "user_consented", False):
                raise PermissionError(
                    "Cloud mode requires an explicitly consented cloud provider "
                    "(user_consented=True). Refusing to route document content externally."
                )
        # Avoid unnecessary reconnection / recreation if state has not changed (WR-02)
        if self.cloud_mode == target_mode:
            if not target_mode and self.provider is not None and self.provider.get_capabilities().is_local:
                return
            if target_mode and (cloud_provider is None or self.provider is cloud_provider):
                return

        self.cloud_mode = target_mode
        if cloud_provider is not None:
            self.cloud_provider = cloud_provider

        self.close()
        self.provider = self._detect_provider()
        self.model_name = self.provider.get_capabilities().model_name

    def _detect_provider(self) -> BaseModelProvider:
        """Select active provider based on local health and explicit cloud_mode.

        When cloud_mode is False (default), stays strictly on local LlamaCppProvider
        without silent external transmission (INF-03, INF-04, CONCERNS.md).
        """
        # 1. If Cloud Mode is explicitly enabled, route through cloud provider
        if self.cloud_mode:
            if self.cloud_provider is None:
                raise PermissionError(
                    "Cloud mode is active without a consented provider; refusing to infer externally."
                )
            return self.cloud_provider

        # 2. Local mode: probe local llama-server
        local = LlamaCppProvider()
        return local

    def check_health(self) -> HealthStatus:
        """Probe the active provider once.

        The previous implementation probed the active provider and, when unhealthy,
        constructed a second identical provider and probed again — doubling the
        latency of every Streamlit rerun while llama-server was offline. Callers that
        render frequently should throttle this call; the UI does so per session.

        Returns:
            HealthStatus schema from active provider.
        """
        return self.provider.check_health()

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
        doc_id: str | None = None,
    ) -> Generator[str, None, None]:
        """Stream answer tokens grounded in retrieved document context.

        Args:
            pdf_path: Path to PDF if building embedding on-the-fly.
            prompt: User question.
            local_embedding: Existing vector index or hybrid retriever instance.
            chat_history: Prior conversation turns.
            retrieval_result: Optional pre-computed canonical RetrievalResult (RETR-04).
            doc_id: Optional document scope used when retrieving internally.

        Yields:
            Token text chunks as generated.
        """
        caps = self.provider.get_capabilities()
        if retrieval_result is not None:
            relevant_sections = retrieval_result.formatted_evidence()
        else:
            if local_embedding is None and pdf_path:
                warnings.warn(
                    "Direct unindexed PDF ingestion in ask_a_question_from_pdf_stream has been deprecated and removed. "
                    "Callers must index documents via DocStore/LanceDB and provide an indexed retriever or explicit RetrievalResult.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                raise ValueError(
                    "Direct unindexed PDF ingestion in ask_a_question_from_pdf_stream has been removed. "
                    "Please provide an indexed retriever (LocalEmbedding or HybridRetriever) or explicit RetrievalResult."
                )

            # Contextualize the search query only when the prompt is a short follow-up.
            # Shared helper keeps the UI and AiModel paths from drifting (CONCERNS.md).
            search_query = contextualize_query(prompt, chat_history)

            if local_embedding:
                if isinstance(local_embedding, HybridRetriever):
                    retrieval_result = resolve_retrieval(
                        local_embedding,
                        search_query,
                        doc_id=doc_id,
                        k=10,
                        max_context_chars=whole_document_char_budget(caps.context_window),
                    )
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

        messages = assemble_grounded_messages(
            prompt=prompt,
            context_text=relevant_sections,
            history=chat_history,
            max_context_tokens=caps.context_window,
            truncation_meta=self.last_truncation_warning,
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
            # Guarantees the gate is released when the stream finishes normally,
            # when the provider raises, and when a consumer abandons the
            # generator and it is closed (GeneratorExit).
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
