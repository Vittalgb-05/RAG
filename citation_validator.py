"""
Automated citation validation and abstention detection for grounded QA.

Validates that all bracketed evidence citations ([E1], [E2]) in assistant responses
strictly correspond to retrieved EvidenceSnippet records, enforcing >= 95% citation
precision (QA-03) and detecting explicit model abstention without citation fabrication (QA-04).
"""

import logging
import re
from pydantic import BaseModel, ConfigDict, Field
from models import RetrievalResult

logger = logging.getLogger(__name__)

CITATION_REGEX = re.compile(r"\[E(\d+)\]", re.IGNORECASE)

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
        message=msg,
    )
