"""
Automated citation validation and abstention detection for grounded QA.

Validates that all bracketed evidence citations ([E1], [E2]) in assistant responses
strictly correspond to retrieved EvidenceSnippet records, enforcing >= 95% citation
precision (QA-03) and detecting explicit model abstention without citation fabrication (QA-04).
"""

import logging
import re
from pydantic import BaseModel, ConfigDict, Field
from core.models import RetrievalResult

logger = logging.getLogger(__name__)

CITATION_REGEX = re.compile(r"\[E(\d+)\]", re.IGNORECASE)

# Lexical support check (no new dependencies). A citation-bearing sentence is
# considered supported when enough of its content tokens also occur in the cited
# snippet(s). The threshold is deliberately conservative: this is a diagnostic,
# not a replacement for rank validity.
SUPPORT_TOKEN_THRESHOLD = 0.35
SUPPORT_MIN_CLAIM_TOKENS = 3
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+|\n+")
SUPPORT_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "as",
        "at",
        "from",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "our",
        "your",
        "we",
        "you",
        "they",
        "he",
        "she",
        "them",
        "his",
        "her",
        "not",
        "no",
        "do",
        "does",
        "did",
        "can",
        "could",
        "should",
        "would",
        "may",
        "might",
        "will",
        "shall",
        "have",
        "has",
        "had",
        "than",
        "then",
        "there",
        "here",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "when",
        "where",
        "why",
        "how",
        "also",
        "such",
        "into",
        "about",
    }
)

CANONICAL_ABSTENTION_MARKERS = [
    "does not contain sufficient evidence",
    "does not contain sufficient information",
    "does not contain information to answer",
    "insufficient information in the provided context",
    "insufficient evidence to answer",
    "insufficient information to answer",
    "cannot find the answer in the document",
    "not enough information in the provided context",
    "not mentioned in the provided document",
    "document does not mention",
    "no information provided in the document",
    "the provided document context does not contain",
    "the document does not contain sufficient evidence",
]

KNOWN_ADVERSARIAL_DIRECTIVES: tuple[str, ...] = (
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard all previous",
    "disregard previous instructions",
    "system prompt:",
    "system prompt leak",
    "developer instructions:",
    "jailbreak successful",
    "dan mode",
    "bypass security controls",
    "you have been hacked",
    "i have been instructed to ignore",
)


class CitationVerificationResult(BaseModel):
    """Result schema for automated response citation precision verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool = Field(..., description="Whether citations meet >= 95% precision or valid abstention.")
    precision: float = Field(..., ge=0.0, le=1.0, description="Citation precision score (0.0 - 1.0).")
    total_citations: int = Field(default=0, ge=0, description="Total unique citation references claimed in text.")
    valid_citations: list[str] = Field(default_factory=list, description="Valid citation tags (e.g. ['[E1]', '[E2]']).")
    hallucinated_citations: list[str] = Field(
        default_factory=list, description="Invalid or out-of-bounds citation tags."
    )
    cited_ranks: list[int] = Field(default_factory=list, description="Sorted list of valid 1-based snippet ranks.")
    abstention_detected: bool = Field(default=False, description="Whether response explicitly abstains from answering.")
    injection_detected: bool = Field(
        default=False, description="Whether adversarial prompt injection directive was detected."
    )
    support_checked: bool = Field(
        default=False, description="Whether the lightweight lexical claim-to-snippet support check ran."
    )
    support_precision: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fraction of citation-bearing sentences whose content lexically overlaps the cited snippet.",
    )
    unsupported_ranks: list[int] = Field(
        default_factory=list,
        description="Cited ranks whose sentences had insufficient lexical support (diagnostic, not rank validity).",
    )
    message: str = Field(default="", description="Human-readable verification diagnostic.")


def detect_adversarial_injection(text: str) -> tuple[bool, str | None]:
    """Detect whether text echoes or executes known adversarial prompt injection directives.

    Args:
        text: Assistant response text.

    Returns:
        Tuple of (is_detected, matched_pattern).
    """
    lower = text.lower().strip()
    for directive in KNOWN_ADVERSARIAL_DIRECTIVES:
        if directive in lower:
            return True, directive
    return False, None


def extract_citations(text: str) -> list[int]:
    """Extract and sort unique 1-based citation ranks from response text.

    Matches patterns like [E1], [E2], [e1], [E1][E2].

    Args:
        text: Assistant response text.

    Returns:
        Sorted list of unique positive integer snippet ranks.
    """
    matches = CITATION_REGEX.findall(text)
    ranks = {int(m) for m in matches if int(m) > 0}
    return sorted(ranks)


def is_abstention(text: str) -> bool:
    """Detect whether a response explicitly abstains due to insufficient document evidence.

    Args:
        text: Assistant response text.

    Returns:
        True if text matches canonical abstention phrases, False otherwise.
    """
    lower = text.lower().strip()
    return any(marker in lower for marker in CANONICAL_ABSTENTION_MARKERS)


def should_withhold_answer(verification: CitationVerificationResult) -> bool:
    """Return True when a generated answer must not be rendered as a normal answer.

    A response is withheld when it fails grounding (no citations), when citations
    are invalid/out-of-range, or when an injection directive was echoed. Explicit
    abstentions remain valid answers and are never withheld.

    Args:
        verification: Citation verification result for the generated response.

    Returns:
        True if the UI should reject/withhold the draft answer.
    """
    if verification.abstention_detected:
        return False
    return not verification.is_valid


def _support_tokens(text: str) -> set[str]:
    """Return lowercase content tokens for the lexical support heuristic."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {token for token in tokens if len(token) >= 2 and token not in SUPPORT_STOPWORDS}


def _evaluate_lexical_support(
    text: str,
    valid_ranks: list[int],
    retrieval_result: RetrievalResult | None,
) -> tuple[bool, float, list[int]]:
    """Check whether cited sentences lexically overlap the snippets they cite.

    This is intentionally a conservative diagnostic rather than a second validity
    gate: rank validity remains the contract that decides ``is_valid`` and
    ``precision``. The result lets the UI distinguish "the citation points at a
    real snippet" from "the snippet actually contains the claim's wording".

    Args:
        text: Assistant response text.
        valid_ranks: Ranks that exist in the retrieval result.
        retrieval_result: Retrieval result holding the cited snippet texts.

    Returns:
        Tuple of (checked, support_precision, unsupported_ranks).
    """
    if not text or not valid_ranks or retrieval_result is None or not retrieval_result.snippets:
        return False, 0.0, []

    valid_rank_set = set(valid_ranks)
    snippet_by_rank = {index: snippet.content for index, snippet in enumerate(retrieval_result.snippets, start=1)}

    evaluable = 0
    supported = 0
    unsupported: set[int] = set()

    for sentence in SENTENCE_SPLIT_REGEX.split(text):
        cited = [rank for rank in extract_citations(sentence) if rank in valid_rank_set]
        if not cited:
            continue

        claim = CITATION_REGEX.sub(" ", sentence)
        claim_tokens = _support_tokens(claim)
        if len(claim_tokens) < SUPPORT_MIN_CLAIM_TOKENS:
            continue

        evaluable += 1
        snippet_tokens: set[str] = set()
        for rank in cited:
            snippet_tokens.update(_support_tokens(snippet_by_rank.get(rank, "")))

        overlap = len(claim_tokens & snippet_tokens) / len(claim_tokens)
        if overlap >= SUPPORT_TOKEN_THRESHOLD:
            supported += 1
        else:
            unsupported.update(cited)

    if evaluable == 0:
        return False, 0.0, []

    return True, supported / evaluable, sorted(unsupported)


def validate_citations(
    response_text: str,
    retrieval_result: RetrievalResult | None = None,
) -> CitationVerificationResult:
    """Validate all generated citations against retrieved evidence records.

    Enforces minimum 95% citation precision (QA-03) and validates abstention (QA-04).

    Args:
        response_text: Assistant response text containing optional [En] citations.
        retrieval_result: Canonical RetrievalResult containing the snippets presented to the model.

    Returns:
        CitationVerificationResult containing precision metrics and diagnostic message.
    """
    text = response_text.strip()

    # 1. Check for empty response (CR-03: empty generation is never valid grounding)
    if not text:
        return CitationVerificationResult(
            is_valid=False,
            precision=0.0,
            total_citations=0,
            valid_citations=[],
            hallucinated_citations=[],
            cited_ranks=[],
            abstention_detected=False,
            message="Empty response: no grounded content generated.",
        )

    ranks = extract_citations(text)
    total_claimed = len(ranks)

    max_valid_rank = len(retrieval_result.snippets) if retrieval_result and retrieval_result.snippets else 0

    # 2. Check for adversarial prompt injection directive echo (Security mitigation)
    has_injection, injection_pattern = detect_adversarial_injection(text)
    if has_injection:
        return CitationVerificationResult(
            is_valid=False,
            precision=0.0,
            total_citations=total_claimed,
            valid_citations=[],
            hallucinated_citations=[f"[E{r}]" for r in ranks],
            cited_ranks=[],
            abstention_detected=False,
            injection_detected=True,
            message=f"Adversarial prompt injection directive detected in output ('{injection_pattern}'). Grounding validation rejected for security.",
        )

    # 3. Check for explicit abstention (QA-04)
    if is_abstention(text):
        if total_claimed == 0:
            return CitationVerificationResult(
                is_valid=True,
                precision=1.0,
                total_citations=0,
                valid_citations=[],
                hallucinated_citations=[],
                cited_ranks=[],
                abstention_detected=True,
                message="Valid explicit abstention without fabricated citations.",
            )
        else:
            hallucinated = [f"[E{r}]" for r in ranks]
            return CitationVerificationResult(
                is_valid=False,
                precision=0.0,
                total_citations=total_claimed,
                valid_citations=[],
                hallucinated_citations=hallucinated,
                cited_ranks=[],
                abstention_detected=True,
                message=f"Abstention contains unexpected citations ({', '.join(hallucinated)}). Abstaining answers must not cite evidence.",
            )

    # 3. Non-abstaining response with 0 citations (Ungrounded)
    if total_claimed == 0:
        return CitationVerificationResult(
            is_valid=False,
            precision=0.0,
            total_citations=0,
            valid_citations=[],
            hallucinated_citations=[],
            cited_ranks=[],
            abstention_detected=False,
            message="Response contains claims without any bracketed [E1] evidence citations.",
        )

    # 4. Evaluate precision against retrieved snippet set (QA-03)
    valid_ranks = [r for r in ranks if 1 <= r <= max_valid_rank]
    hallucinated_ranks = [r for r in ranks if r < 1 or r > max_valid_rank]

    valid_tags = [f"[E{r}]" for r in valid_ranks]
    hallucinated_tags = [f"[E{r}]" for r in hallucinated_ranks]

    precision = len(valid_ranks) / total_claimed
    is_valid = precision >= 0.95

    support_checked, support_precision, unsupported_ranks = _evaluate_lexical_support(
        text, valid_ranks, retrieval_result
    )

    if is_valid:
        msg = f"Citation precision {precision:.1%} ({len(valid_ranks)}/{total_claimed} citations verified)."
    else:
        msg = (
            f"Citation precision {precision:.1%} failed >=95% requirement: hallucinated {', '.join(hallucinated_tags)}."
        )

    return CitationVerificationResult(
        is_valid=is_valid,
        precision=precision,
        total_citations=total_claimed,
        valid_citations=valid_tags,
        hallucinated_citations=hallucinated_tags,
        cited_ranks=valid_ranks,
        abstention_detected=False,
        support_checked=support_checked,
        support_precision=support_precision,
        unsupported_ranks=unsupported_ranks,
        message=msg,
    )


def auto_attribute_citations(
    text: str,
    retrieval_result: RetrievalResult | None,
    min_overlap: float = 0.18,
) -> str:
    """Attribute candidate evidence citations ([E#]) to sentences in an uncited draft.

    When local language models generate accurate answers grounded in document context
    but omit inline citation tags [E#], this function scans sentences for lexical
    overlap with retrieved snippets and appends the best matching [E#] citations.

    Args:
        text: Assistant draft text.
        retrieval_result: Retrieved candidate evidence records.
        min_overlap: Minimum token overlap fraction to attribute a snippet (default 0.18).

    Returns:
        Draft text with grounded [E#] citations appended to matching sentences, or original text if no matches.
    """
    if not text or not text.strip():
        return text

    # If the response already contains any [E#] citations, do not alter it.
    if extract_citations(text):
        return text

    # Abstentions must never cite evidence.
    if is_abstention(text):
        return text

    if retrieval_result is None or not retrieval_result.snippets:
        return text

    snippet_tokens: list[tuple[int, set[str]]] = []
    for rank, snippet in enumerate(retrieval_result.snippets, start=1):
        content = snippet.content or ""
        tokens = _support_tokens(content)
        if tokens:
            snippet_tokens.append((rank, tokens))

    if not snippet_tokens:
        return text

    # Split into paragraphs to preserve structure
    paragraphs = text.split("\n")
    attributed_paragraphs = []
    any_cited = False

    for paragraph in paragraphs:
        if not paragraph.strip():
            attributed_paragraphs.append(paragraph)
            continue

        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        attributed_sentences = []

        for sent in sentences:
            sent_trimmed = sent.strip()
            claim_tokens = _support_tokens(sent_trimmed)

            if len(claim_tokens) < SUPPORT_MIN_CLAIM_TOKENS:
                attributed_sentences.append(sent)
                continue

            best_rank = None
            best_overlap = 0.0

            for rank, s_tokens in snippet_tokens:
                overlap = len(claim_tokens & s_tokens) / max(len(claim_tokens), 1)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_rank = rank

            if best_rank is not None and best_overlap >= min_overlap:
                any_cited = True
                if sent_trimmed.endswith((".", "!", "?")):
                    new_sent = sent_trimmed[:-1].rstrip() + f" [E{best_rank}]" + sent_trimmed[-1]
                else:
                    new_sent = sent_trimmed + f" [E{best_rank}]"
                attributed_sentences.append(new_sent)
            else:
                attributed_sentences.append(sent)

        attributed_paragraphs.append(" ".join(attributed_sentences))

    if any_cited:
        return "\n".join(attributed_paragraphs)
    return text
