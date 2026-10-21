"""Shared query intent, follow-up contextualization, and whole-document evidence selection.

Centralizes the short-follow-up heuristic that previously lived in both `ui/views.py`
and `core/local_llm.py`, detects enumeration/extraction questions that cannot be
answered from a fixed top-k chunk sample (e.g. "What are the questions?"), and
selects page-diverse evidence that fits the conservative 4K context budget.
"""

import re
from typing import Any

from core.models import EvidenceSnippet, RetrievalResult

# Verbs/pronouns that make a short prompt a follow-up rather than a new question.
FOLLOWUP_TOKENS: frozenset[str] = frozenset(
    {
        "it",
        "that",
        "this",
        "these",
        "those",
        "they",
        "them",
        "why",
        "how",
        "more",
        "elaborate",
        "details",
    }
)

# Plural document entities that are commonly requested as a complete inventory.
_INVENTORY_NOUNS = (
    r"(?:questions?|exercises?|problems?|topics?|chapters?|sections?|items?|"
    r"terms?|definitions?|findings?|key\s+points?|requirements?|instructions?)"
)

_WHOLE_DOCUMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "What are the questions?", "Which topics were covered?"
    re.compile(rf"\b(?:what|which)\s+(?:are|were)\s+(?:all\s+)?(?:of\s+)?(?:the\s+)?{_INVENTORY_NOUNS}\b"),
    # "What questions does the document ask?"
    re.compile(rf"\bwhat\s+{_INVENTORY_NOUNS}\s+(?:are|does|were|did)\b"),
    # "List/extract/enumerate all the questions"
    re.compile(
        rf"\b(?:list|extract|enumerate|identify|name|provide|give|show)\b[^?.!]*?"
        rf"\b(?:all|every|each|the)\b[^?.!]*?\b{_INVENTORY_NOUNS}\b"
    ),
    # "All the questions", "every exercise"
    re.compile(rf"\ball\s+(?:of\s+)?(?:the\s+)?{_INVENTORY_NOUNS}\b"),
    re.compile(r"\b(?:every|each)\s+(?:single\s+)?(?:question|exercise|problem|topic|item)\b"),
    # Whole-document scope requests
    re.compile(r"\b(?:whole|entire|full)\s+(?:document|pdf|book|booklet)\b"),
    re.compile(r"\bsummar(?:y|ize|ise)\s+(?:the\s+)?(?:whole|entire|full)\s+(?:document|pdf|book)\b"),
)


def contextualize_query(prompt: str, history: list[dict[str, Any]] | None) -> str:
    """Prefix the previous user question onto an ambiguous short follow-up.

    This is the single source of truth for follow-up rewriting used by both the
    chat view (before retrieval) and `AiModel` (when it retrieves internally).

    Args:
        prompt: Current user prompt.
        history: Prior chat turns (may be None or contain non-string content).

    Returns:
        Search query, unchanged unless the prompt is a short follow-up with history.
    """
    if not prompt or not history:
        return prompt

    tokens = re.findall(r"[a-z0-9']+", prompt.lower())
    if len(tokens) > 4 or not any(t in FOLLOWUP_TOKENS for t in tokens):
        return prompt

    last_user_msgs = [
        message["content"]
        for message in history
        if isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(message.get("content"), str)
        and message["content"].strip()
    ]
    if not last_user_msgs:
        return prompt
    return f"{last_user_msgs[-1]} {prompt}"


def is_whole_document_query(query: str) -> bool:
    """Return True when the query asks for a complete document-level inventory.

    Only explicit enumeration/extraction phrasing qualifies. Normal targeted
    questions ("What are the primary findings of section 2?") stay on top-k
    hybrid retrieval, so this does not turn chat into a summarizer.

    Args:
        query: User question or contextualized search query.

    Returns:
        True if the query should retrieve all chunks in document/page order.
    """
    if not query or not query.strip():
        return False
    lowered = query.lower()
    return any(pattern.search(lowered) for pattern in _WHOLE_DOCUMENT_PATTERNS)


def whole_document_char_budget(context_window: int = 4096, max_output_tokens: int = 1024) -> int:
    """Estimate characters of evidence that fit alongside the grounding system prompt.

    Args:
        context_window: Provider context window in tokens.
        max_output_tokens: Tokens reserved for generation.

    Returns:
        Conservative character budget for page-diverse evidence selection.
    """
    # ~4 chars/token, minus ~400 tokens for the system contract and user prompt.
    return max(2000, (max(0, context_window - max_output_tokens - 400)) * 4)


def select_page_diverse_snippets(
    snippets: list[EvidenceSnippet],
    max_chars: int,
) -> list[EvidenceSnippet]:
    """Select evidence that covers every page before filling remaining budget.

    Whole-document questions fail when a blind prefix truncation drops later pages.
    This picks one snippet per page first (in page order), then a second per page,
    and so on. Selected snippets are re-ranked contiguously from 1 so citation
    validation (`max_valid_rank == len(snippets)`) stays consistent.

    Args:
        snippets: Page-ordered document snippets.
        max_chars: Maximum total characters of snippet content to retain.

    Returns:
        Re-ranked snippets preserving page coverage within the budget.
    """
    if not snippets or max_chars <= 0:
        return []

    groups: dict[int, list[tuple[int, EvidenceSnippet]]] = {}
    for index, snippet in enumerate(snippets):
        groups.setdefault(snippet.page, []).append((index, snippet))

    pages = sorted(groups)
    picks: list[tuple[int, EvidenceSnippet, str]] = []
    used = 0

    # First pass: guarantee one item per page by splitting the budget evenly.
    # Without this, a few large early chunks can consume the whole budget and
    # later pages never appear in the prompt.
    per_page_budget = max_chars // max(1, len(pages))
    for page in pages:
        page_items = groups[page]
        if not page_items:
            continue
        original_index, snippet = page_items[0]
        text = snippet.content.strip()
        if len(text) > per_page_budget:
            if per_page_budget < 40:
                continue
            text = text[: per_page_budget - 21].rstrip() + "\n[... truncated ...]"
        picks.append((original_index, snippet, text))
        used += len(text)

    # Additional passes: spend any leftovers on second/third chunks per page.
    round_index = 1
    while used < max_chars:
        made_progress = False
        for page in pages:
            page_items = groups[page]
            if round_index >= len(page_items):
                continue
            made_progress = True
            original_index, snippet = page_items[round_index]
            remaining = max_chars - used
            if remaining <= 0:
                break
            text = snippet.content.strip()
            if len(text) > remaining:
                if remaining < 200:
                    break
                text = text[: remaining - 20].rstrip() + "\n[... truncated ...]"
            picks.append((original_index, snippet, text))
            used += len(text)
        if not made_progress:
            break
        round_index += 1

    picks.sort(key=lambda item: item[0])
    selected: list[EvidenceSnippet] = []
    for rank, (_, snippet, text) in enumerate(picks, start=1):
        updates: dict[str, Any] = {"rank": rank, "content": text}
        if snippet.char_start is not None:
            updates["char_end"] = snippet.char_start + len(text)
        selected.append(snippet.model_copy(update=updates))
    return selected


def resolve_retrieval(
    retriever: Any,
    query: str,
    doc_id: str | list[str] | None = None,
    k: int = 8,
    max_context_chars: int | None = None,
) -> RetrievalResult:
    """Retrieve evidence, switching to page-ordered whole-document scope when needed.

    Args:
        retriever: HybridRetriever or LocalEmbedding-compatible retriever.
        query: Contextualized search query.
        doc_id: Optional document ID scope.
        k: Top-k for ordinary retrieval.
        max_context_chars: Character budget for whole-document selection.

    Returns:
        Canonical RetrievalResult whose snippet ranks match the prompt evidence.
    """
    if isinstance(doc_id, str) and doc_id and is_whole_document_query(query):
        fetch = getattr(retriever, "fetch_document_chunks", None)
        if callable(fetch):
            document_result = fetch(doc_id)
            if document_result.snippets:
                budget = max_context_chars or whole_document_char_budget()
                selected = select_page_diverse_snippets(document_result.snippets, budget)
                if selected:
                    return document_result.model_copy(update={"query": query, "snippets": selected})

    if hasattr(retriever, "search_hybrid"):
        return retriever.search_hybrid(query, k=k, doc_id=doc_id)
    raise TypeError(f"Retriever {type(retriever).__name__} does not support search_hybrid().")
