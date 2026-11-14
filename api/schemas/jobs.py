"""Background job schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel
from api.schemas.common import Problem

JobKind = Literal["ingest", "reindex", "summarize"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class JobResponse(BaseModel):
    """Job status response."""

    job_id: str
    kind: str
    status: JobStatus
    stage: str
    pct: float | None = None
    message: str = ""
    result: object | None = None
    error: Problem | None = None
    created_at: str | None = None
    updated_at: str | None = None
