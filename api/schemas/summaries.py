"""Document summary schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

SummaryProfile = Literal["overview", "detailed", "study_notes", "tables_figures", "findings"]
SummaryLength = Literal["concise", "standard", "detailed"]


class SummaryRequest(BaseModel):
    """Payload to generate a document summary."""

    doc_id: str
    profile: SummaryProfile = "overview"
    length: SummaryLength = "standard"
    force: bool = False


class SummaryResponse(BaseModel):
    """Generated or cached document summary."""

    doc_id: str
    profile: str
    summary: str
    model_version: str
    cached: bool = False
    job_id: str | None = None
