"""Hybrid search and Retrieval X-Ray router."""

from __future__ import annotations
from fastapi import APIRouter, Depends

from api.container import AppContainer
from api.deps import get_container
from api.schemas.common import Source
from api.schemas.search import ExplanationItem, SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_endpoint(
    body: SearchRequest,
    c: AppContainer = Depends(get_container),
) -> SearchResponse:
    """Execute hybrid retrieval across documents with optional X-Ray ranking breakdown."""
    doc_filter = body.doc_ids if body.doc_ids else None
    result = c.retriever.search_hybrid(
        query=body.query,
        k=body.k,
        doc_id=doc_filter,
        explain=body.explain,
    )

    sources: list[Source] = []
    for s in result.snippets:
        sources.append(
            Source(
                rank=s.rank,
                doc_id=s.doc_id,
                filename=s.filename,
                page=s.page,
                preview=s.content[:200],
                score=s.score,
                cited=False,
                supported=None,
                bbox=list(s.bbox.model_dump().values()) if s.bbox else None,
            )
        )

    explanations: list[ExplanationItem] | None = None
    if body.explain and result.explanation:
        explanations = [
            ExplanationItem(
                chunk_id=e["chunk_id"],
                doc_id=e["doc_id"],
                dense_rank=e.get("dense_rank"),
                dense_score=e.get("dense_score"),
                fts_rank=e.get("fts_rank"),
                fts_score=e.get("fts_score"),
                rrf_score=e.get("rrf_score", 0.0),
            )
            for e in result.explanation
        ]

    return SearchResponse(
        query=body.query,
        sources=sources,
        explanations=explanations,
    )
