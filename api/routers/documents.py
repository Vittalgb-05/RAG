"""Document management, ingestion, and page retrieval endpoints."""

from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from api.container import AppContainer
from api.deps import get_container
from api.errors import ApiError
from api.jobs import JobHandle
from api.schemas.documents import (
    DocumentDetail,
    DocumentJobItem,
    DocumentSummary,
    DocumentUploadResponse,
)
from api.schemas.jobs import JobResponse
from core.limits import MAX_FILE_MB
from ingestion.upload_validation import validate_pdf_bytes

router = APIRouter(tags=["documents"])


@router.get("/documents", response_model=list[DocumentSummary])
async def list_documents(c: AppContainer = Depends(get_container)) -> list[DocumentSummary]:
    """List all documents currently registered in the catalog."""
    docs = c.doc_store.list_documents()
    evidence_counts = c.doc_store.get_evidence_counts_batch()
    summaries: list[DocumentSummary] = []
    for d in docs:
        has_vec = c.retriever.has_document(d.doc_id) if d.status == "indexed" else False
        status_val: Literal["pending", "indexing", "indexed", "failed"] = (
            d.status if d.status in ("pending", "indexing", "indexed", "failed") else "failed"
        )
        summaries.append(
            DocumentSummary(
                doc_id=d.doc_id,
                filename=d.filename,
                sha256=d.sha256,
                status=status_val,
                pages=d.num_pages,
                chunks=d.num_chunks,
                evidence_elements=evidence_counts.get(d.doc_id, 0),
                size_bytes=d.size_bytes,
                created_at=d.upload_time,
                has_vectors=has_vec,
            )
        )
    return summaries


@router.post("/documents", status_code=202, response_model=DocumentUploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    c: AppContainer = Depends(get_container),
) -> DocumentUploadResponse:
    """Upload one or more PDF files and queue asynchronous ingestion jobs."""
    job_items: list[DocumentJobItem] = []

    max_bytes = MAX_FILE_MB * 1024 * 1024
    for file_obj in files:
        if file_obj.size is not None and file_obj.size > max_bytes:
            raise ApiError(
                status_code=413,
                code="upload_too_large",
                detail=f"File '{file_obj.filename}' exceeds maximum allowed size of {MAX_FILE_MB}MB.",
            )
        raw_bytes = await file_obj.read()
        if len(raw_bytes) > max_bytes:
            raise ApiError(
                status_code=413,
                code="upload_too_large",
                detail=f"File '{file_obj.filename}' exceeds maximum allowed size of {MAX_FILE_MB}MB.",
            )
        filename = file_obj.filename or "uploaded.pdf"

        # Validate headers, size, and page limits synchronously
        validated = validate_pdf_bytes(raw_bytes, filename)
        doc_id = validated.doc_id
        sha256 = validated.sha256

        # Persist original PDF for Evidence Lens page image rendering
        if c.settings.store_originals:
            orig_dir = c.settings.data_dir / "originals"
            orig_dir.mkdir(parents=True, exist_ok=True)
            orig_file = orig_dir / f"{sha256}.pdf"
            if not orig_file.exists():
                orig_file.write_bytes(raw_bytes)

        # Fast deduplication check
        existing = c.doc_store.get_by_sha(sha256)
        if (
            existing
            and existing.status == "indexed"
            and existing.num_chunks > 0
            and c.retriever.has_document(existing.doc_id)
        ):
            job_items.append(
                DocumentJobItem(
                    job_id="",
                    filename=existing.filename or filename,
                    doc_id=existing.doc_id,
                    duplicate=True,
                )
            )
            continue

        # Submit background ingestion job with VLM provider if vision is supported
        caps = c.ai_model.get_capabilities()
        vlm = c.ai_model if getattr(caps, "supports_vision", False) else None

        def run_ingest(handle: JobHandle, raw: bytes = raw_bytes, name: str = filename, vlm_provider=vlm):
            return c.ingestion.ingest_pdf(
                raw,
                name,
                vlm_provider=vlm_provider,
                progress_callback=lambda stage, pct: handle.progress(stage, pct),
            )

        job = c.jobs.submit(
            "ingest",
            run_ingest,
            doc_id=doc_id,
            filename=filename,
        )
        job_items.append(
            DocumentJobItem(
                job_id=job.job_id,
                filename=filename,
                doc_id=doc_id,
                duplicate=False,
            )
        )

    return DocumentUploadResponse(jobs=job_items)


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str, c: AppContainer = Depends(get_container)) -> DocumentDetail:
    """Retrieve document details, chunks, and evidence elements."""
    doc = c.doc_store.get_document(doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")

    chunks = c.doc_store.get_chunks_for_doc(doc_id)
    evidence = c.doc_store.get_evidence_for_doc(doc_id)

    return DocumentDetail(
        doc_id=doc.doc_id,
        filename=doc.filename,
        sha256=doc.sha256,
        status=doc.status,
        num_pages=doc.num_pages,
        num_chunks=doc.num_chunks,
        size_bytes=doc.size_bytes,
        upload_time=doc.upload_time,
        chunks=[c.model_dump() for c in chunks],
        evidence=[e.model_dump() for e in evidence],
    )


@router.get("/documents/{doc_id}/pages/{page_num}")
async def get_document_page(
    doc_id: str,
    page_num: int,
    c: AppContainer = Depends(get_container),
) -> dict[str, object]:
    """Retrieve text content for a specific page."""
    page = c.doc_store.get_page(doc_id, page_num)
    if not page:
        raise ApiError(
            status_code=404,
            code="not_found",
            detail=f"Page {page_num} for document '{doc_id}' not found.",
        )
    text = getattr(page, "page_text", None) or ""
    if not text:
        chunks = [ch for ch in c.doc_store.get_chunks_for_doc(doc_id) if ch.page == page_num]
        if chunks:
            text = "\n\n".join(ch.content for ch in chunks)
    return {
        "doc_id": doc_id,
        "page_num": page.page_num,
        "page_number": page.page_num,
        "text": text,
        "char_count": page.char_count or len(text),
    }


@router.get("/documents/{doc_id}/evidence")
async def get_document_evidence(
    doc_id: str,
    c: AppContainer = Depends(get_container),
) -> list[dict[str, object]]:
    """Retrieve visual evidence elements (figures, tables) for a document."""
    elements = c.doc_store.get_evidence_for_doc(doc_id)
    return [e.model_dump() for e in elements]


@router.get("/documents/{doc_id}/pages/{page_num}/image")
async def get_page_image(
    doc_id: str,
    page_num: int,
    c: AppContainer = Depends(get_container),
):
    """Render page image for Evidence Lens if original PDF is available."""
    doc = c.doc_store.get_document(doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")

    orig_path = c.settings.data_dir / "originals" / f"{doc.sha256}.pdf"
    if not orig_path.exists():
        raise ApiError(
            status_code=404,
            code="not_found",
            detail="Original PDF not stored. Set RAG_STORE_ORIGINALS=1 to enable page image rendering.",
        )

    try:
        import fitz  # PyMuPDF

        with fitz.open(orig_path) as doc_fitz:
            if page_num < 1 or page_num > len(doc_fitz):
                raise ApiError(status_code=404, code="not_found", detail=f"Page {page_num} out of bounds.")
            page = doc_fitz.load_page(page_num - 1)
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            return Response(content=img_bytes, media_type="image/png")
    except ImportError:
        raise ApiError(
            status_code=501,
            code="unsupported_operation",
            detail="PyMuPDF is required to render page images.",
        ) from None


@router.post("/documents/{doc_id}/reindex", response_model=JobResponse)
async def reindex_document(doc_id: str, c: AppContainer = Depends(get_container)) -> JobResponse:
    """Trigger background re-indexing of an existing document."""
    doc = c.doc_store.get_document(doc_id)
    if not doc:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")

    def run_reindex(handle: JobHandle):
        handle.progress("reindex", 10, "Starting reindex...")
        ok = c.lifecycle.reindex_document(doc_id)
        if not ok:
            raise RuntimeError(f"Re-indexing failed for {doc_id}")
        handle.progress("reindex", 100, "Re-indexing complete")
        return {"reindexed": True}

    job = c.jobs.submit("reindex", run_reindex, doc_id=doc_id)
    return JobResponse(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,  # type: ignore[arg-type]
        stage=job.stage,
        pct=job.pct,
        message=job.message,
    )


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, c: AppContainer = Depends(get_container)) -> dict[str, bool]:
    """Delete a document across SQLite, LanceDB, and disk cache."""
    deleted = c.lifecycle.delete_document(doc_id)
    if not deleted:
        raise ApiError(status_code=404, code="not_found", detail=f"Document '{doc_id}' not found.")
    return {"deleted": True}


@router.delete("/documents")
async def purge_all_documents(
    confirm: str = Query(..., description="Must be 'PURGE'"),
    c: AppContainer = Depends(get_container),
) -> dict[str, bool]:
    """Completely purge all documents, vectors, caches, and chat sessions."""
    if confirm != "PURGE":
        raise ApiError(
            status_code=400,
            code="confirmation_required",
            detail="You must supply confirm=PURGE query parameter to purge the library.",
        )
    c.lifecycle.purge_all()
    return {"purged": True}
