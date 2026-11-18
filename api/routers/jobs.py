"""Background job monitoring and cancellation endpoints."""

from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.container import AppContainer
from api.deps import get_container
from api.errors import ApiError
from api.schemas.jobs import JobResponse
from api.streaming import SSE_HEADERS

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(c: AppContainer = Depends(get_container)) -> list[JobResponse]:
    """List recent background jobs and their current status."""
    jobs = c.jobs.list_jobs()
    return [
        JobResponse(
            job_id=j.job_id,
            kind=j.kind,
            status=j.status,  # type: ignore[arg-type]
            stage=j.stage,
            pct=j.pct,
            message=j.message,
            result=j.result,
            created_at=j.created_at,
            updated_at=j.updated_at,
        )
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, c: AppContainer = Depends(get_container)) -> JobResponse:
    """Retrieve details and progress of a specific job."""
    j = c.jobs.get(job_id)
    if not j:
        raise ApiError(status_code=404, code="not_found", detail=f"Job '{job_id}' not found.")
    return JobResponse(
        job_id=j.job_id,
        kind=j.kind,
        status=j.status,  # type: ignore[arg-type]
        stage=j.stage,
        pct=j.pct,
        message=j.message,
        result=j.result,
        created_at=j.created_at,
        updated_at=j.updated_at,
    )


@router.get("/jobs/{job_id}/events")
async def stream_job_events(job_id: str, c: AppContainer = Depends(get_container)):
    """Stream live progress and completion events for a background job over SSE."""
    j = c.jobs.get(job_id)
    if not j:
        raise ApiError(status_code=404, code="not_found", detail=f"Job '{job_id}' not found.")

    return StreamingResponse(c.jobs.events(job_id), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, c: AppContainer = Depends(get_container)) -> dict[str, bool]:
    """Request cooperative cancellation of a running or queued job."""
    cancelled = c.jobs.cancel(job_id)
    if not cancelled:
        raise ApiError(status_code=404, code="not_found", detail=f"Job '{job_id}' not found.")
    return {"cancelled": True}
