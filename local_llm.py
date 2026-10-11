"""AI Model interface delegating to BaseModelProvider implementations.

Provides unified streaming response generation, bounded context budgeting,
prompt injection isolation (<document_context>), and resilient fallback between
local llama-server (Qwen3-VL 2B GGUF) and cloud Groq inference.
"""

from collections.abc import Generator
from groq_provider import GroqProvider
from llama_cpp_provider import LlamaCppProvider
from local_embedding import LocalEmbedding
from model_provider import BaseModelProvider, HealthStatus, ProviderCapabilities
from pdf_reader import PdfReader
from prompt_budget import assemble_grounded_messages


class AiModel:
    """Orchestrates document Q&A inference across local or cloud providers."""

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
        local_embedding: LocalEmbedding | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> Generator[str, None, None]:
        """Stream answer tokens grounded in retrieved document context.

        Args:
            pdf_path: Path to PDF if building embedding on-the-fly.
            prompt: User question.
            local_embedding: Existing vector index instance.
            chat_history: Prior conversation turns.

        Yields:
            Token text chunks as generated.
        """
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

        retrieval_result = None
        if local_embedding:
            if hasattr(local_embedding, "search_hybrid"):
                retrieval_result = local_embedding.search_hybrid(search_query, k=10)
                relevant_sections = retrieval_result.formatted_evidence()
            else:
                relevant_sections = local_embedding.get_context(search_query, k=10)
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

        yield from self.provider.stream_text(
            prompt=bounded_prompt,
            system_prompt=system_prompt,
            history=history_turns,
            max_tokens=1024,
        )
