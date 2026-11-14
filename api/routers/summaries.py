"""Document summarization and summary cache endpoints."""

from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from api.container import AppContainer
from api.deps import get_container
from api.errors import ApiError
from api.jobs import JobHandle
from api.schemas.summaries import SummaryRequest, SummaryResponse
from core.summarizer import Summarizer, compute_summary_model_version

router = APIRouter(tags=["summaries"])


@router.get("/summaries", response_model=SummaryResponse)
async def get_summary_query(
    doc_id: str = Query(...),
    profile: str = Query(default="overview"),
    length: str = Query(default="standard"),
    c: AppContainer = Depends(get_container),
) -> SummaryResponse:
    """Retrieve cached summary for a document and profile."""
    return await get_summary_by_path(doc_id, profile, length, c)


@router.get("/summaries/{doc_id}/{profile}", response_model=SummaryResponse)
async def get_summary_by_path(
    doc_id: str,
    profile: str,
    length: str = Query(default="standard"),
    c: AppContainer = Depends(get_container),
) -> SummaryResponse:
    """Retrieve cached summary for a document and profile."""
    doc = c.doc_store.get_document(doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")

    caps = c.ai_model.get_capabilities()
    model_name = getattr(caps, "model_name", "local")
    model_ver = compute_summary_model_version(model_name, length)

    cached = c.doc_store.get_summary(doc.sha256, profile=profile, model_version=model_ver)
    if not cached:
        raise ApiError(
            status_code=404,
            code="not_found",
            detail=f"No cached summary for '{doc_id}' with profile '{profile}' and length '{length}'.",
        )

    return SummaryResponse(
        doc_id=doc_id,
        profile=profile,
        summary=cached.summary_text,
        model_version=cached.model_version,
        cached=True,
    )


@router.get("/summaries/{doc_id}/{profile}/export")
async def export_summary(
    doc_id: str,
    profile: str,
    length: str = Query(default="standard"),
    format: str = Query(default="md"),
    c: AppContainer = Depends(get_container),
):
    """Export document summary as markdown."""
    summary_resp = await get_summary_by_path(doc_id, profile, length, c)
    return PlainTextResponse(summary_resp.summary, media_type="text/markdown")


@router.post("/summaries", response_model=SummaryResponse)
async def create_summary(
    body: SummaryRequest,
    c: AppContainer = Depends(get_container),
) -> SummaryResponse:
    """Generate or retrieve a cached document summary asynchronously."""
    doc = c.doc_store.get_document(body.doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{body.doc_id}' not found.")

    caps = c.ai_model.get_capabilities()
    model_name = getattr(caps, "model_name", "local")
    model_ver = compute_summary_model_version(model_name, body.length)

    if not body.force:
        cached = c.doc_store.get_summary(doc.sha256, profile=body.profile, model_version=model_ver)
        if cached:
            return SummaryResponse(
                doc_id=body.doc_id,
                profile=body.profile,
                summary=cached.summary_text,
                model_version=cached.model_version,
                cached=True,
            )

    pages = c.doc_store.get_pages_for_doc(body.doc_id)
    if not pages:
        raise ApiError(
            status_code=422,
            code="empty_document",
            detail=f"Document '{body.doc_id}' has no stored page text to summarize.",
        )

    full_text = "\n\n".join(p.text for p in pages if p.text)

    def run_summary(handle: JobHandle):
        handle.progress("summarize", 10, "Starting document summary...")
        summarizer = Summarizer(doc_store=c.doc_store, ai_model=c.ai_model)
        result = summarizer.summarize_document(
            raw_text=full_text,
            doc_id=body.doc_id,
            sha256=doc.sha256,
            profile=body.profile,
            length=body.length,
            force_refresh=body.force,
            progress=lambda done, total, msg: handle.progress(
                "summarize",
                round((done / max(1, total)) * 100, 1),
                msg,
            ),
            cancel=handle.cancelled,
        )
        return {
            "summary": result.summary_text,
            "profile": body.profile,
            "doc_id": body.doc_id,
        }

    job = c.jobs.submit(
        "summarize",
        run_summary,
        doc_id=body.doc_id,
        profile=body.profile,
        length=body.length,
    )

    return SummaryResponse(
        doc_id=body.doc_id,
        profile=body.profile,
        summary="",
        model_version=model_ver,
        cached=False,
        job_id=job.job_id,
    )


@router.delete("/summaries/{doc_id}")
async def clear_document_summaries(
    doc_id: str,
    c: AppContainer = Depends(get_container),
) -> dict[str, bool]:
    """Delete all cached summaries for a document."""
    doc = c.doc_store.get_document(doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")

    c.doc_store.delete_summaries_for_doc(doc_id)
    return {"deleted": True}
