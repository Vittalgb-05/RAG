"""Document Constellation 3D visualization and query tracing endpoints."""

from __future__ import annotations
import numpy as np
from fastapi import APIRouter, Depends, Query
from starlette.concurrency import run_in_threadpool

from api.container import AppContainer
from api.deps import get_container
from api.schemas.visualize import (
    EmbeddingPoint,
    EmbeddingsResponse,
    QueryTraceRequest,
    QueryTraceResponse,
)

router = APIRouter(tags=["visualize"])

# Global cache for PCA projection basis: (basis, mean, doc_ids_hash)
_PROJECTION_CACHE: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def _project_to_3d(vectors: list[list[float]]) -> tuple[list[list[float]], np.ndarray, np.ndarray]:
    """Reduce high-dimensional embedding vectors to 3D coordinates via PCA (NumPy SVD)."""
    if not vectors:
        return [], np.zeros((1, 3)), np.zeros((1,))

    arr = np.array(vectors, dtype=np.float32)
    n, d = arr.shape
    mean = np.mean(arr, axis=0)
    centered = arr - mean

    if n < 3:
        # Fallback for fewer than 3 samples
        coords = np.zeros((n, 3), dtype=np.float32)
        if d >= 3:
            coords[:, :] = centered[:, :3]
        basis = np.eye(d, 3, dtype=np.float32)
        return coords.tolist(), basis, mean

    # SVD: centered = U * S * Vt
    try:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        basis = vt[:3].T  # shape (d, 3)
        projected = np.dot(centered, basis)
        return projected.tolist(), basis, mean
    except Exception:
        # Fallback: simple first 3 dimensions
        coords = centered[:, :3] if d >= 3 else np.pad(centered, ((0, 0), (0, 3 - d)))
        basis = np.eye(d, 3, dtype=np.float32)
        return coords.tolist(), basis, mean


@router.get("/visualize/embeddings", response_model=EmbeddingsResponse)
async def get_embeddings_constellation(
    doc_ids: str | None = Query(default=None),
    dims: int = Query(default=3, ge=2, le=3),
    limit: int = Query(default=3000, ge=10, le=5000),
    c: AppContainer = Depends(get_container),
) -> EmbeddingsResponse:
    """Export 3D-projected chunk embeddings for the Document Constellation."""
    id_list = [d.strip() for d in doc_ids.split(",") if d.strip()] if doc_ids else None
    c_ids, vectors, metadata = await run_in_threadpool(
        c.retriever.export_embeddings,
        doc_ids=id_list,
        limit=limit,
    )

    if not vectors:
        return EmbeddingsResponse(points=[], dims=dims, total_points=0)

    projected_coords, basis, mean = await run_in_threadpool(_project_to_3d, vectors)
    _PROJECTION_CACHE["last"] = (basis, mean)

    points: list[EmbeddingPoint] = []
    for cid, coord, meta in zip(c_ids, projected_coords, metadata, strict=False):
        points.append(
            EmbeddingPoint(
                chunk_id=cid,
                doc_id=meta.get("doc_id", ""),
                filename=meta.get("filename", ""),
                point=[round(float(v), 4) for v in coord[:dims]],
                page=meta.get("page"),
                preview=meta.get("preview", ""),
            )
        )

    return EmbeddingsResponse(points=points, dims=dims, total_points=len(points))


@router.post("/visualize/query-trace", response_model=QueryTraceResponse)
async def trace_query(
    body: QueryTraceRequest,
    c: AppContainer = Depends(get_container),
) -> QueryTraceResponse:
    """Project query into constellation coordinates and trace retrieved chunk candidates."""
    # 1. Embed query
    query_embs = await run_in_threadpool(c.embedding.get_embeddings, [body.query])
    query_emb = query_embs[0]

    # 2. Project into current PCA space if available, or compute on the fly
    if "last" in _PROJECTION_CACHE:
        basis, mean = _PROJECTION_CACHE["last"]
        if len(query_emb) == len(mean):
            centered = query_emb - mean
            q_point = np.dot(centered, basis).tolist()
        else:
            q_point = [0.0, 0.0, 0.0]
    else:
        q_point = [0.0, 0.0, 0.0]

    # 3. Retrieve top candidates
    res = await run_in_threadpool(c.retriever.search_hybrid, body.query, k=body.k, doc_id=body.doc_ids)
    candidate_ids = [s.chunk_id for s in res.snippets if s.chunk_id]

    return QueryTraceResponse(
        point=[round(float(v), 4) for v in q_point[:3]],
        retrieved_chunk_ids=candidate_ids,
    )
