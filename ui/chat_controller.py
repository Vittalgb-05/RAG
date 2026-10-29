"""Framework-independent chat-turn orchestration for the document assistant.

This module deliberately does not import Streamlit. The view owns session state,
widgets, token streaming, rendering, and reruns; this service owns scope
resolution, retrieval invocation, pipeline selection (QA vs document-wide
summary), auto-attribution, bounded regeneration, and citation verification,
returning typed results for the view to render.

Grounding contract: each preparation and result carries a ``GroundingReport``
with the request id, resolved scope, document IDs, evidence count, citations,
verification status/reason, and an incomplete-context flag. The UI renders
sources and grounding labels only from this report, never from a separate
retrieval result.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.citation_validator import CitationVerificationResult, auto_attribute_citations, should_withhold_answer
from core.models import EvidenceSnippet, GroundingReport, RetrievalResult
from core.query_intent import (
    answer_states_current_location,
    asks_for_current_location,
    contextualize_query,
    evidence_states_current_location,
    is_summary_request,
    resolve_retrieval,
    select_page_diverse_snippets,
    whole_document_char_budget,
)
from core.redaction import redact_text

INSUFFICIENT_EVIDENCE_MESSAGE = "The document does not contain sufficient evidence to answer this question."
REGENERATION_PROMPT = (
    "Your previous answer contained claims that the supplied evidence does not support. "
    "Rewrite the answer using only facts explicitly stated in the evidence blocks. "
    "Cite every claim with its matching [E#] tag. Omit any point the evidence does not state. "
    "Do not introduce new topics, examples, or outside knowledge."
)


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
    request_id: str = ""
    mode: str = "qa"
    scope: str = "none"
    document_ids: list[str] = field(default_factory=list)
    incomplete_context: bool = False
    abstention_reason: str | None = None


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
    error_message: str | None = None
    request_id: str = ""
    mode: str = "qa"
    report: GroundingReport | None = None


def _build_report(
    preparation: ChatTurnPreparation,
    verification: CitationVerificationResult,
    *,
    auto_attributed_count: int = 0,
    regeneration_attempted: bool = False,
) -> GroundingReport:
    """Assemble the single request/result grounding contract for one turn."""
    return GroundingReport(
        request_id=preparation.request_id or f"req_{uuid.uuid4().hex[:16]}",
        mode="summary" if preparation.mode == "summary" else "qa",
        scope=preparation.scope,  # type: ignore[arg-type]
        document_ids=list(preparation.document_ids),
        evidence_count=len(preparation.snippets),
        cited_ranks=list(verification.cited_ranks or []),
        verification_status=verification.grounding_status,
        verification_reason=verification.message,
        unsupported_ranks=list(verification.unsupported_ranks),
        auto_attributed_count=auto_attributed_count,
        incomplete_context=preparation.incomplete_context,
        regeneration_attempted=regeneration_attempted,
    )


class ChatTurnService:
    """Resolve chat scope and finalize grounded answers without UI dependencies."""

    def __init__(self, validator: CitationValidator, *, k: int = 10) -> None:
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
        """Resolve document scope and retrieve evidence for one user prompt.

        Summary requests take a different evidence path from QA: one selected
        document is read end-to-end (page-ordered, page-diverse within budget) and
        chat history is dropped so a previous document's turns cannot leak in.
        """
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        history = list(history_before_turn[-10:])
        search_query = contextualize_query(prompt, history)
        mode = "summary" if is_summary_request(search_query) else "qa"

        doc_filter = selected_doc
        if doc_filter is None and document_metadata:
            doc_filter = self._detect_document_mention(prompt, document_metadata)

        retrieval_scope = doc_filter
        if retrieval_scope is None and len(document_metadata) == 1:
            retrieval_scope = next(iter(document_metadata))

        incomplete_context = False
        abstention_reason: str | None = None
        if mode == "summary":
            # Summary requests cannot silently fall back to top-k or all-document
            # search: an unscoped summary would blend evidence across documents.
            history = []
            if not isinstance(retrieval_scope, str) or not retrieval_scope:
                retrieval_result = RetrievalResult(
                    query=search_query,
                    snippets=[],
                    total_candidates=0,
                    search_mode="intent_mismatch",
                )
                return ChatTurnPreparation(
                    prompt=prompt,
                    history=history,
                    search_query=search_query,
                    doc_filter=doc_filter,
                    retrieval_scope=None,
                    retrieval_result=retrieval_result,
                    sources=[],
                    snippets=[],
                    intent_mismatch=True,
                    chunk_cap_reached=False,
                    request_id=request_id,
                    mode=mode,
                    scope="all_documents" if document_metadata else "none",
                    document_ids=list(document_metadata),
                    incomplete_context=False,
                    abstention_reason=None,
                )
            retrieval_result, sources, incomplete_context = self._retrieve_document_wide(
                retriever=retriever,
                search_query=search_query,
                doc_id=retrieval_scope,
                context_window=context_window,
            )
        else:
            retrieval_result, sources = self._retrieve(
                retriever=retriever,
                search_query=search_query,
                retrieval_scope=retrieval_scope,
                context_window=context_window,
            )
            if retrieval_result is not None and retrieval_result.snippets and asks_for_current_location(search_query):
                evidence_text = "\n".join(snippet.content for snippet in retrieval_result.snippets)
                if not evidence_states_current_location(evidence_text):
                    # Answering with an employer, school, or historical city would
                    # be a related fact, not the requested present location.
                    abstention_reason = (
                        "The question asks for a current location, but the retrieved evidence "
                        "does not explicitly state a residence or base location."
                    )

        snippets = (
            [snippet.model_dump() for snippet in retrieval_result.snippets]
            if retrieval_result is not None and retrieval_result.snippets
            else []
        )

        if isinstance(retrieval_scope, str) and retrieval_scope:
            scope = "document"
            document_ids = [retrieval_scope]
        elif document_metadata:
            scope = "all_documents"
            document_ids = list(document_metadata)
        else:
            scope = "none"
            document_ids = []

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
            request_id=request_id,
            mode=mode,
            scope=scope,
            document_ids=document_ids,
            incomplete_context=incomplete_context,
            abstention_reason=abstention_reason,
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
        regenerate: Callable[[str], str] | None = None,
    ) -> ChatTurnResult:
        """Attribute citations, validate grounding, and build the assistant turn.

        If the cited claims are mostly unsupported, a single bounded regeneration
        is attempted through ``regenerate``. If that still fails support, the turn
        abstains instead of rendering unsupported claims as a verified answer.
        """
        full_response, auto_attributed_count, auto_attributed_ranks = self._attribute(
            full_response, preparation.retrieval_result
        )

        verification = self._validator(full_response, preparation.retrieval_result)
        verification = verification.model_copy(
            update={
                "auto_attributed_count": auto_attributed_count,
                "auto_attributed_ranks": auto_attributed_ranks,
            }
        )

        regeneration_attempted = False

        def _location_mismatch(answer: str) -> bool:
            return (
                asks_for_current_location(preparation.search_query)
                and not answer_states_current_location(answer)
                and not verification.abstention_detected
            )

        location_mismatch = _location_mismatch(full_response)

        if (
            regenerate is not None
            and verification.grounding_status == "unsupported"
            and preparation.snippets
            and not verification.abstention_detected
            and not location_mismatch
        ):
            regeneration_attempted = True
            corrected = regenerate(REGENERATION_PROMPT) or ""
            corrected, retry_auto_count, retry_auto_ranks = self._attribute(corrected, preparation.retrieval_result)
            retry_verification = self._validator(corrected, preparation.retrieval_result)
            retry_verification = retry_verification.model_copy(
                update={
                    "auto_attributed_count": retry_auto_count,
                    "auto_attributed_ranks": retry_auto_ranks,
                }
            )
            full_response = corrected
            verification = retry_verification
            auto_attributed_count = retry_auto_count
            auto_attributed_ranks = retry_auto_ranks
            location_mismatch = _location_mismatch(full_response)

        if location_mismatch:
            # The generated answer is supported by real evidence but answers a
            # different question (for example, an employer instead of a current
            # location). An abstention is the only truthful outcome.
            auto_attributed_count = 0
            auto_attributed_ranks = []
            verification = verification.model_copy(
                update={
                    "is_valid": True,
                    "precision": 1.0,
                    "total_citations": 0,
                    "valid_citations": [],
                    "hallucinated_citations": [],
                    "cited_ranks": [],
                    "unsupported_ranks": [],
                    "support_verified": False,
                    "auto_attributed_count": 0,
                    "auto_attributed_ranks": [],
                    "grounding_status": "abstained",
                    "message": (
                        "The question asks for a current location, but the answer does not state one. "
                        "Abstaining rather than substituting a related fact."
                    ),
                }
            )

        if on_response_ready is not None and not location_mismatch:
            on_response_ready(full_response)

        verification_dict = verification.model_dump()
        report = _build_report(
            preparation,
            verification,
            auto_attributed_count=auto_attributed_count,
            regeneration_attempted=regeneration_attempted,
        )

        withheld = should_withhold_answer(verification) or location_mismatch
        injection_detected = bool(getattr(verification, "injection_detected", False))
        if injection_detected:
            content_to_save = "[Response withheld: prompt injection detected.]"
            rejected = True
        elif location_mismatch:
            content_to_save = INSUFFICIENT_EVIDENCE_MESSAGE
            rejected = True
        elif withheld:
            # Bounded regeneration already ran (or was unavailable). Abstain rather
            # than present unsupported claims with real-looking citations.
            content_to_save = INSUFFICIENT_EVIDENCE_MESSAGE
            rejected = True
        else:
            content_to_save = full_response
            rejected = False

        unverified = withheld and not injection_detected and not location_mismatch
        truncation = dict(truncation_warning or {})
        cited_ranks = list(verification.cited_ranks or [])

        assistant_turn = {
            "role": "assistant",
            "content": content_to_save,
            "rejected": rejected,
            "unverified": unverified,
            "injection_detected": injection_detected,
            "sources": list(preparation.sources),
            "verification": verification_dict,
            "grounding_report": report.model_dump(),
            "snippets": preparation.snippets,
            "truncation_warning": truncation,
            "is_cloud": is_cloud,
            "model_name": model_name,
            "request_id": report.request_id,
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
            chunk_cap_reached=preparation.chunk_cap_reached or preparation.incomplete_context,
            sources=list(preparation.sources),
            snippets=preparation.snippets,
            truncation_warning=truncation,
            is_cloud=is_cloud,
            model_name=model_name,
            request_id=report.request_id,
            mode=preparation.mode,
            report=report,
        )

    @staticmethod
    def _attribute(
        text: str,
        retrieval_result: RetrievalResult | None,
    ) -> tuple[str, int, list[int]]:
        """Auto-attribute strong lexical matches and return added ranks."""
        if retrieval_result is None or not retrieval_result.snippets:
            return text, 0, []
        original_citations = set(re.findall(r"\[E(\d+)\]", text, re.IGNORECASE))
        attributed = auto_attribute_citations(text, retrieval_result)
        if attributed == text:
            return text, 0, []
        new_citations = set(re.findall(r"\[E(\d+)\]", attributed, re.IGNORECASE))
        added_ranks = new_citations - original_citations
        return attributed, len(added_ranks), sorted(int(rank) for rank in added_ranks)

    def error_result(
        self,
        preparation: ChatTurnPreparation,
        error: BaseException,
        *,
        truncation_warning: dict[str, bool] | None = None,
        is_cloud: bool = False,
        model_name: str = "",
    ) -> ChatTurnResult:
        """Build a redacted, persistable assistant turn for a failed generation."""
        error_message = redact_text(str(error))
        content = f"*[Response generation interrupted: {error_message}]*"
        truncation = dict(truncation_warning or {})
        report = GroundingReport(
            request_id=preparation.request_id or f"req_{uuid.uuid4().hex[:16]}",
            mode="summary" if preparation.mode == "summary" else "qa",
            scope=preparation.scope,  # type: ignore[arg-type]
            document_ids=list(preparation.document_ids),
            evidence_count=len(preparation.snippets),
            verification_status="ungrounded",
            verification_reason="Generation failed before citations could be verified.",
            incomplete_context=preparation.incomplete_context,
        )
        assistant_turn = {
            "role": "assistant",
            "content": content,
            "rejected": False,
            "unverified": True,
            "sources": list(preparation.sources),
            "verification": None,
            "grounding_report": report.model_dump(),
            "snippets": preparation.snippets,
            "truncation_warning": truncation,
            "is_cloud": is_cloud,
            "model_name": model_name,
            "request_id": report.request_id,
        }
        return ChatTurnResult(
            content=content,
            response_text=content,
            assistant_turn=assistant_turn,
            verification=None,
            cited_ranks=[],
            auto_attributed_count=0,
            auto_attributed_ranks=[],
            withheld=False,
            injection_detected=False,
            unverified=True,
            rejected=False,
            chunk_cap_reached=preparation.chunk_cap_reached,
            sources=list(preparation.sources),
            snippets=preparation.snippets,
            truncation_warning=truncation,
            is_cloud=is_cloud,
            model_name=model_name,
            error_message=error_message,
            request_id=report.request_id,
            mode=preparation.mode,
            report=report,
        )

    def intent_mismatch_result(self, preparation: ChatTurnPreparation) -> ChatTurnResult:
        """Build the non-answer turn shown when a summary/exhaustive request needs one document."""
        message = (
            "Select a single document in the scope dropdown to summarize or extract across the whole document."
            if preparation.mode == "summary"
            else "[Please select a specific document to run exhaustive extraction.]"
        )
        report = GroundingReport(
            request_id=preparation.request_id or f"req_{uuid.uuid4().hex[:16]}",
            mode="summary" if preparation.mode == "summary" else "qa",
            scope=preparation.scope,  # type: ignore[arg-type]
            document_ids=list(preparation.document_ids),
            evidence_count=0,
            verification_status="abstained",
            verification_reason="Request needs a single-document scope before evidence can be retrieved.",
        )
        assistant_turn = {
            "role": "assistant",
            "content": message,
            "rejected": False,
            "sources": [],
            "snippets": [],
            "verification": {},
            "grounding_report": report.model_dump(),
            "truncation_warning": {},
            "request_id": report.request_id,
        }
        return ChatTurnResult(
            content=message,
            response_text=message,
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
            request_id=report.request_id,
            mode=preparation.mode,
            report=report,
        )

    def abstention_result(self, preparation: ChatTurnPreparation) -> ChatTurnResult:
        """Build the deterministic abstention turn for a known-unanswerable facet."""
        reason = preparation.abstention_reason or (
            "The retrieved evidence does not state the specific detail this question asks for."
        )
        report = GroundingReport(
            request_id=preparation.request_id or f"req_{uuid.uuid4().hex[:16]}",
            mode="summary" if preparation.mode == "summary" else "qa",
            scope=preparation.scope,  # type: ignore[arg-type]
            document_ids=list(preparation.document_ids),
            evidence_count=len(preparation.snippets),
            verification_status="abstained",
            verification_reason=reason,
            incomplete_context=preparation.incomplete_context,
        )
        verification = {
            "is_valid": True,
            "precision": 1.0,
            "total_citations": 0,
            "valid_citations": [],
            "hallucinated_citations": [],
            "cited_ranks": [],
            "abstention_detected": True,
            "injection_detected": False,
            "support_checked": False,
            "support_precision": 0.0,
            "unsupported_ranks": [],
            "support_verified": False,
            "uncited_claim_count": 0,
            "uncited_unsupported_count": 0,
            "grounding_status": "abstained",
            "message": reason,
            "auto_attributed_count": 0,
            "auto_attributed_ranks": [],
        }
        assistant_turn = {
            "role": "assistant",
            "content": INSUFFICIENT_EVIDENCE_MESSAGE,
            "rejected": False,
            "unverified": False,
            "injection_detected": False,
            "sources": [],
            "snippets": [],
            "verification": verification,
            "grounding_report": report.model_dump(),
            "truncation_warning": {},
            "request_id": report.request_id,
        }
        return ChatTurnResult(
            content=INSUFFICIENT_EVIDENCE_MESSAGE,
            response_text=INSUFFICIENT_EVIDENCE_MESSAGE,
            assistant_turn=assistant_turn,
            verification=verification,
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
            request_id=report.request_id,
            mode=preparation.mode,
            report=report,
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

    def _retrieve_document_wide(
        self,
        *,
        retriever: Any | None,
        search_query: str,
        doc_id: str,
        context_window: int,
    ) -> tuple[RetrievalResult | None, list[str], bool]:
        """Read one document end-to-end and fit it to the context budget.

        Returns the scoped result, its source labels, and whether any evidence was
        truncated or capped (so the UI can warn about incomplete context).
        """
        if retriever is None:
            return None, [], False

        fetch = getattr(retriever, "fetch_document_chunks", None)
        if not callable(fetch):
            result, sources = self._retrieve(
                retriever=retriever,
                search_query=search_query,
                retrieval_scope=doc_id,
                context_window=context_window,
            )
            return result, sources, bool(result is None or result.chunk_cap_reached)

        document_result = fetch(doc_id)
        snippets = [snippet for snippet in document_result.snippets if snippet.content.strip()]
        if not snippets:
            return (
                RetrievalResult(query=search_query, snippets=[], total_candidates=0, search_mode="document"),
                [],
                False,
            )

        # A page that already produced extractable text is summarized from that
        # text. VLM descriptions are lossy annotations of individual figures and
        # can dominate a small model's summary when they happen to use academic
        # wording (for example, a resume flowchart described as an "algorithm").
        # Keep visual evidence only for pages that have no text at all, so
        # figure-only pages still contribute.
        text_snippets = [snippet for snippet in snippets if snippet.extraction != "vlm"]
        text_pages = {snippet.page for snippet in text_snippets}
        visual_snippets = [
            snippet for snippet in snippets if snippet.extraction == "vlm" and snippet.page not in text_pages
        ]
        summaries_source = text_snippets + visual_snippets
        if not summaries_source:
            summaries_source = snippets

        budget = whole_document_char_budget(context_window)
        selected = select_page_diverse_snippets(summaries_source, budget)
        if not selected:
            selected = summaries_source

        original_by_chunk = {snippet.chunk_id: snippet for snippet in summaries_source}
        incomplete = (
            bool(document_result.chunk_cap_reached)
            or len(selected) < len(summaries_source)
            or any(
                len(chosen.content) < len(original_by_chunk[chosen.chunk_id].content)
                for chosen in selected
                if chosen.chunk_id in original_by_chunk
            )
        )
        result = document_result.model_copy(update={"query": search_query, "snippets": selected})
        return result, result.source_labels(), incomplete

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


__all__ = [
    "INSUFFICIENT_EVIDENCE_MESSAGE",
    "ChatTurnPreparation",
    "ChatTurnResult",
    "ChatTurnService",
    "EvidenceSnippet",
]
