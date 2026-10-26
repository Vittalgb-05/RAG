"""Framework-independent chat-turn orchestration for the document assistant.

This module deliberately does not import Streamlit. The view owns session state,
widgets, token streaming, rendering, and reruns; this service owns scope
resolution, retrieval invocation, auto-attribution, and citation verification,
returning typed results for the view to render.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from core.citation_validator import CitationVerificationResult, auto_attribute_citations, should_withhold_answer
from core.models import RetrievalResult
from core.query_intent import contextualize_query, resolve_retrieval, whole_document_char_budget


class CitationValidator(Protocol):
    """Callable contract matching ``AiModel.validate_response``."""

    def __call__(
        self,
        response_text: str,
        retrieval_result: RetrievalResult | None,
    ) -> CitationVerificationResult: ...


@dataclass(frozen=True)
class ChatTurnPreparation:
    """Scope and evidence resolved before the model starts streaming."""

    prompt: str
    history: list[dict[str, Any]]
    search_query: str
    doc_filter: str | None
    retrieval_scope: str | None
    retrieval_result: RetrievalResult | None
    sources: list[str]
    snippets: list[dict[str, Any]]
    intent_mismatch: bool
    chunk_cap_reached: bool


@dataclass(frozen=True)
class ChatTurnResult:
    """Final assistant turn plus the metadata the view needs to render it."""

    content: str
    response_text: str
    assistant_turn: dict[str, Any]
    verification: dict[str, Any] | None
    cited_ranks: list[int]
    auto_attributed_count: int
    auto_attributed_ranks: list[int]
    withheld: bool
    injection_detected: bool
    unverified: bool
    rejected: bool
    chunk_cap_reached: bool
    sources: list[str]
    snippets: list[dict[str, Any]]
    truncation_warning: dict[str, bool]
    is_cloud: bool
    model_name: str


class ChatTurnService:
    """Resolve chat scope and finalize grounded answers without UI dependencies."""

    def __init__(self, validator: CitationValidator, *, k: int = 8) -> None:
        self._validator = validator
        self._k = k

    def prepare(
        self,
        *,
        prompt: str,
        history_before_turn: list[dict[str, Any]],
        selected_doc: str | None,
        document_metadata: dict[str, dict[str, Any]],
        retriever: Any | None,
        context_window: int,
    ) -> ChatTurnPreparation:
        """Resolve document scope and retrieve evidence for one user prompt."""
        history = list(history_before_turn[-10:])
        search_query = contextualize_query(prompt, history)

        doc_filter = selected_doc
        if doc_filter is None and document_metadata:
            doc_filter = self._detect_document_mention(prompt, document_metadata)

        retrieval_scope = doc_filter
        if retrieval_scope is None and len(document_metadata) == 1:
            retrieval_scope = next(iter(document_metadata))

        retrieval_result, sources = self._retrieve(
            retriever=retriever,
            search_query=search_query,
            retrieval_scope=retrieval_scope,
            context_window=context_window,
        )

        snippets = (
            [snippet.model_dump() for snippet in retrieval_result.snippets]
            if retrieval_result is not None and retrieval_result.snippets
            else []
        )

        return ChatTurnPreparation(
            prompt=prompt,
            history=history,
            search_query=search_query,
            doc_filter=doc_filter,
            retrieval_scope=retrieval_scope,
            retrieval_result=retrieval_result,
            sources=sources,
            snippets=snippets,
            intent_mismatch=bool(retrieval_result is not None and retrieval_result.search_mode == "intent_mismatch"),
            chunk_cap_reached=bool(
                retrieval_result is not None and getattr(retrieval_result, "chunk_cap_reached", False)
            ),
        )

    def finalize(
        self,
        preparation: ChatTurnPreparation,
        full_response: str,
        *,
        truncation_warning: dict[str, bool] | None = None,
        is_cloud: bool = False,
        model_name: str = "",
        on_response_ready: Callable[[str], None] | None = None,
    ) -> ChatTurnResult:
        """Attribute citations, validate grounding, and build the assistant turn."""
        auto_attributed_count = 0
        auto_attributed_ranks: list[int] = []

        if preparation.retrieval_result is not None and preparation.retrieval_result.snippets:
            original_citations = set(re.findall(r"\[E(\d+)\]", full_response, re.IGNORECASE))
            attributed = auto_attribute_citations(full_response, preparation.retrieval_result)
            if attributed != full_response:
                full_response = attributed
                new_citations = set(re.findall(r"\[E(\d+)\]", full_response, re.IGNORECASE))
                added_ranks = new_citations - original_citations
                auto_attributed_count = len(added_ranks)
                auto_attributed_ranks = sorted(int(rank) for rank in added_ranks)

        if on_response_ready is not None:
            on_response_ready(full_response)

        verification = self._validator(full_response, preparation.retrieval_result)
        verification_dict = verification.model_dump()
        verification_dict["auto_attributed_count"] = auto_attributed_count

        withheld = should_withhold_answer(verification)
        injection_detected = bool(getattr(verification, "injection_detected", False))
        if injection_detected:
            content_to_save = "[Response withheld: prompt injection detected.]"
            rejected = True
        else:
            content_to_save = full_response
            rejected = False

        unverified = withheld and not injection_detected
        truncation = dict(truncation_warning or {})
        cited_ranks = list(verification.cited_ranks or [])

        assistant_turn = {
            "role": "assistant",
            "content": content_to_save,
            "rejected": rejected,
            "unverified": unverified,
            "injection_detected": injection_detected,
            "sources": list(preparation.sources),
            "verification": verification.model_dump(),
            "snippets": preparation.snippets,
            "truncation_warning": truncation,
            "is_cloud": is_cloud,
            "model_name": model_name,
        }

        return ChatTurnResult(
            content=content_to_save,
            response_text=full_response,
            assistant_turn=assistant_turn,
            verification=verification_dict,
            cited_ranks=cited_ranks,
            auto_attributed_count=auto_attributed_count,
            auto_attributed_ranks=auto_attributed_ranks,
            withheld=withheld,
            injection_detected=injection_detected,
            unverified=unverified,
            rejected=rejected,
            chunk_cap_reached=preparation.chunk_cap_reached,
            sources=list(preparation.sources),
            snippets=preparation.snippets,
            truncation_warning=truncation,
            is_cloud=is_cloud,
            model_name=model_name,
        )

    def intent_mismatch_result(self, preparation: ChatTurnPreparation) -> ChatTurnResult:
        """Build the non-answer turn shown when exhaustive intent needs one document."""
        assistant_turn = {
            "role": "assistant",
            "content": "[Please select a specific document to run exhaustive extraction.]",
            "rejected": False,
            "sources": [],
            "snippets": [],
            "verification": {},
            "truncation_warning": {},
        }
        return ChatTurnResult(
            content=assistant_turn["content"],
            response_text=assistant_turn["content"],
            assistant_turn=assistant_turn,
            verification=None,
            cited_ranks=[],
            auto_attributed_count=0,
            auto_attributed_ranks=[],
            withheld=False,
            injection_detected=False,
            unverified=False,
            rejected=False,
            chunk_cap_reached=preparation.chunk_cap_reached,
            sources=[],
            snippets=[],
            truncation_warning={},
            is_cloud=False,
            model_name="",
        )

    def _retrieve(
        self,
        *,
        retriever: Any | None,
        search_query: str,
        retrieval_scope: str | None,
        context_window: int,
    ) -> tuple[RetrievalResult | None, list[str]]:
        if retriever is None:
            return None, []

        if hasattr(retriever, "search_hybrid"):
            result = resolve_retrieval(
                retriever,
                search_query,
                doc_id=retrieval_scope,
                k=self._k,
                max_context_chars=whole_document_char_budget(context_window),
            )
            return result, result.source_labels()

        results = retriever.search(search_query, k=10)
        sources: list[str] = []
        seen_sources: set[str] = set()
        for doc, _ in results:
            filename = doc.get("filename")
            if filename and filename not in seen_sources:
                seen_sources.add(filename)
                sources.append(filename)
        return None, sources

    @staticmethod
    def _detect_document_mention(
        prompt: str,
        document_metadata: dict[str, dict[str, Any]],
    ) -> str | None:
        prompt_lower = prompt.lower()
        for doc_id, meta in document_metadata.items():
            filename = str(meta.get("filename", "")).lower()
            if not filename:
                continue
            stem = Path(filename).stem.lower()
            if filename in prompt_lower or (len(stem) >= 3 and stem in prompt_lower):
                return doc_id
        return None
