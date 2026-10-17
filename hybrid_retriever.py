"""Persistent hybrid retrieval using LanceDB and CPU-pinned embeddings.

Provides serverless on-disk vector storage, full-text keyword indexing (BM25),
and Reciprocal Rank Fusion (RRF), with graceful in-memory fallback when LanceDB
is unavailable (RETR-01, RETR-02, RETR-03, RETR-04).
"""

from collections.abc import Callable
import json
import logging
import math
from pathlib import Path
import re
from typing import Any
import warnings

from models import BBox, Chunk, EvidenceSnippet, RetrievalResult
from vector_index import VectorIndex

logger = logging.getLogger(__name__)

# Optional LanceDB import
try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore[assignment]
    pa = None  # type: ignore[assignment]


def _escape_sql_literal(value: str) -> str:
    """Escape single quotes in string literals for LanceDB SQL filter clauses (CR-03)."""
    return str(value).replace("'", "''")


DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"
DEFAULT_RRF_K = 60


def compute_rrf(
    dense_ranks: list[tuple[str, int, float]],
    fts_ranks: list[tuple[str, int, float]],
    k_rrf: int = DEFAULT_RRF_K,
) -> list[tuple[str, float, int, int | None, int | None]]:
    """Compute Reciprocal Rank Fusion across dense and FTS ranked lists (RETR-03).

    Formula:
        RRF_score(d) = sum_{m in {dense, fts}} 1 / (k_rrf + rank_m(d))

    Args:
        dense_ranks: List of (chunk_id, 1-based rank, raw_score) from dense vector search.
        fts_ranks: List of (chunk_id, 1-based rank, raw_score) from full-text keyword search.
        k_rrf: Smoothing parameter (standard literature default: 60).

    Returns:
        List of tuples sorted by descending composite RRF score:
        (chunk_id, rrf_score, final_rank, dense_rank_or_None, fts_rank_or_None)
    """
    scores: dict[str, float] = {}
    d_ranks: dict[str, int] = {}
    f_ranks: dict[str, int] = {}

    for chunk_id, rank, _ in dense_ranks:
        d_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k_rrf + rank))

    for chunk_id, rank, _ in fts_ranks:
        f_ranks[chunk_id] = rank
        scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k_rrf + rank))

    sorted_chunks = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    results: list[tuple[str, float, int, int | None, int | None]] = []

    for final_rank, (chunk_id, rrf_score) in enumerate(sorted_chunks, start=1):
        results.append(
            (
                chunk_id,
                rrf_score,
                final_rank,
                d_ranks.get(chunk_id),
                f_ranks.get(chunk_id),
            )
        )

    return results


class HybridRetriever:
    """Persistent on-disk vector and hybrid retrieval service backed by LanceDB."""

    def __init__(
        self,
        db_uri: Path | str | None = None,
        embedding_fn: Callable[[str], list[float]] | None = None,
        vector_dim: int = 384,
    ) -> None:
        """Initialize the hybrid retriever.

        Args:
            db_uri: Local filesystem directory for persistent LanceDB tables.
                    Defaults to <repo_root>/data/lancedb.
            embedding_fn: Optional callable to embed a query string into a vector.
            vector_dim: Dimensionality of dense embedding vectors (384 for all-MiniLM-L6-v2).
        """
        self.db_uri = Path(db_uri) if db_uri is not None else DEFAULT_DB_URI
        self.embedding_fn = embedding_fn
        self.vector_dim = vector_dim

        self._has_lancedb = lancedb is not None
        self._db: Any = None
        self._table: Any = None

        # Pure-Python in-memory fallback store
        self._fallback_store = VectorIndex(
            distance_metric="cosine",
            embedding_fn=self.embedding_fn,
        )

        self._fallback_file = self.db_uri / "fallback_store.json"

        if self._has_lancedb:
            try:
                self.db_uri.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(str(self.db_uri))
                self._init_table()
                logger.info("LanceDB persistent retriever connected at %s", self.db_uri)
            except Exception as err:
                logger.warning("Failed to initialize LanceDB at %s: %s. Using in-memory fallback.", self.db_uri, err)
                self._has_lancedb = False
                self._load_fallback_store()
        else:
            logger.info("LanceDB not installed. Operating in disk-backed fallback mode at %s.", self.db_uri)
            self._load_fallback_store()

    def _load_fallback_store(self) -> None:
        """Load stored vectors and documents from disk when LanceDB is unavailable."""
        if not self._fallback_file.exists():
            return
        try:
            with open(self._fallback_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            docs = data.get("documents", [])
            vecs = data.get("vectors", [])
            for doc, vec in zip(docs, vecs):
                self._fallback_store.add_vector(vec, doc)
            logger.info("Loaded %d chunks from fallback persistent store at %s", len(docs), self._fallback_file)
        except Exception as err:
            logger.warning("Failed to load fallback store: %s", err)

    def set_embedding_fn(self, embedding_fn: Callable[[str], list[float]]) -> None:
        """Set or update the embedding function used for query vectorization."""
        self.embedding_fn = embedding_fn
        if hasattr(self._fallback_store, "_embedding_fn"):
            self._fallback_store._embedding_fn = embedding_fn

    def close(self) -> None:
        """Flush fallback persistence and release database handles."""
        if not self._has_lancedb or self._db is None:
            self._save_fallback_store()
        self._table = None
        self._db = None

    def __enter__(self) -> "HybridRetriever":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _save_fallback_store(self) -> None:
        """Persist fallback store to disk."""
        try:
            self.db_uri.mkdir(parents=True, exist_ok=True)
            serializable_docs = []
            for d in self._fallback_store.documents:
                doc_copy = dict(d)
                bbox = doc_copy.get("bbox")
                if isinstance(bbox, BBox):
                    doc_copy["bbox"] = bbox.model_dump()
                elif hasattr(bbox, "model_dump"):
                    doc_copy["bbox"] = bbox.model_dump()
                serializable_docs.append(doc_copy)

            with open(self._fallback_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "documents": serializable_docs,
                        "vectors": self._fallback_store.vectors,
                    },
                    f,
                )
        except Exception as err:
            logger.warning("Failed to save fallback store: %s", err)

    def _init_table(self) -> None:
        """Connect to existing 'chunks' table if present."""
        if not self._has_lancedb or self._db is None:
            return
        try:
            # Check if table already exists in the LanceDB database
            existing_tables = self._db.table_names()
            if "chunks" in existing_tables:
                self._table = self._db.open_table("chunks")
                logger.info("Opened existing LanceDB 'chunks' table (%d rows).", len(self._table))
        except Exception as err:
            logger.warning("Error checking or opening LanceDB table: %s", err)

    def is_persistent(self) -> bool:
        """Return True if persistent on-disk LanceDB backend is active."""
        return self._has_lancedb and self._db is not None

    def count_chunks(self) -> int:
        """Return total number of chunks currently indexed."""
        if self._has_lancedb and self._table is not None:
            try:
                return len(self._table)
            except Exception:
                pass
        return len(self._fallback_store.documents)

    def has_document(self, doc_id: str) -> bool:
        """Check if any chunks for the given doc_id exist in the index."""
        if self._has_lancedb and self._table is not None:
            try:
                safe_doc_id = _escape_sql_literal(doc_id)
                results = self._table.search().where(f"doc_id = '{safe_doc_id}'").limit(1).to_list()
                return len(results) > 0
            except Exception:
                pass
        return any(d.get("doc_id") == doc_id for d in self._fallback_store.documents)

    contains_document = has_document

    def purge_all(self) -> None:
        """Purge all stored vectors, chunks, and LanceDB tables across persistent and fallback stores."""
        if self._has_lancedb and self._db is not None:
            try:
                existing_tables = self._db.table_names()
                if "chunks" in existing_tables:
                    self._db.drop_table("chunks")
                    logger.info("Dropped LanceDB 'chunks' table.")
            except Exception as err:
                logger.warning("Error dropping LanceDB 'chunks' table: %s", err)
            self._table = None

        self._fallback_store = VectorIndex(
            distance_metric="cosine",
            embedding_fn=self.embedding_fn,
        )
        if self._fallback_file.exists():
            try:
                self._fallback_file.unlink(missing_ok=True)
                logger.info("Unlinked fallback persistent file at %s", self._fallback_file)
            except OSError as err:
                logger.warning("Failed to remove fallback file %s: %s", self._fallback_file, err)

    def index_chunks(
        self,
        chunks: list[dict[str, Any] | Chunk],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """Embed and persist chunks into LanceDB or fallback vector index.

        Args:
            chunks: List of canonical Chunk instances or chunk dictionaries.
            embeddings: Optional pre-computed embedding vectors. If None,
                        self.embedding_fn will be used to compute them.

        Returns:
            Number of chunks successfully indexed.
        """
        if not chunks:
            return 0

        # Normalize chunks to dicts
        raw_chunks: list[dict[str, Any]] = []
        for c in chunks:
            if isinstance(c, Chunk):
                raw_chunks.append(c.model_dump())
            elif isinstance(c, dict):
                raw_chunks.append(dict(c))
            else:
                raise TypeError(f"Expected Chunk or dict, got {type(c).__name__}")

        # Compute embeddings if missing
        if embeddings is None:
            if self.embedding_fn is None:
                raise ValueError("Cannot index chunks: neither embeddings nor embedding_fn was provided.")
            computed_embeddings = [self.embedding_fn(c.get("content", "")) for c in raw_chunks]
        else:
            computed_embeddings = embeddings

        if len(raw_chunks) != len(computed_embeddings):
            raise ValueError(
                f"Mismatch: {len(raw_chunks)} chunks provided but {len(computed_embeddings)} embeddings provided."
            )

        # 1. Update in-memory fallback index with chunk deduplication
        existing_indices = {
            d.get("chunk_id"): i for i, d in enumerate(self._fallback_store.documents) if d.get("chunk_id")
        }
        for doc, emb in zip(raw_chunks, computed_embeddings):
            cid = doc.get("chunk_id")
            if cid and cid in existing_indices:
                idx = existing_indices[cid]
                self._fallback_store.documents[idx] = doc
                self._fallback_store.vectors[idx] = emb
            else:
                self._fallback_store.add_vector(emb, doc)
                if cid:
                    existing_indices[cid] = len(self._fallback_store.documents) - 1

        # 2. Update persistent LanceDB table
        if self._has_lancedb and self._db is not None:
            records: list[dict[str, Any]] = []
            for doc, emb in zip(raw_chunks, computed_embeddings):
                bbox = doc.get("bbox")
                bbox_json = doc.get("bbox_json")
                if bbox_json is None and bbox is not None:
                    if hasattr(bbox, "model_dump_json"):
                        bbox_json = bbox.model_dump_json()
                    elif isinstance(bbox, dict):
                        bbox_json = json.dumps(bbox)

                records.append(
                    {
                        "chunk_id": str(doc.get("chunk_id", "")),
                        "doc_id": str(doc.get("doc_id", "")),
                        "filename": str(doc.get("filename", "")),
                        "page": int(doc.get("page", 1)),
                        "content": str(doc.get("content", "")),
                        "vector": [float(v) for v in emb],
                        "extraction": str(doc.get("extraction", "docling")),
                        "char_start": doc.get("char_start"),
                        "char_end": doc.get("char_end"),
                        "bbox_json": bbox_json,
                    }
                )

            try:
                if self._table is None:
                    # Create new table
                    self._table = self._db.create_table("chunks", data=records, mode="create")
                    logger.info("Created new LanceDB 'chunks' table with %d records.", len(records))
                else:
                    # Upsert using merge_insert if supported, or deduplicated append
                    if hasattr(self._table, "merge_insert"):
                        (
                            self._table.merge_insert("chunk_id")
                            .when_matched_update_all()
                            .when_not_matched_insert_all()
                            .execute(records)
                        )
                    else:
                        chunk_ids = [r["chunk_id"] for r in records if r["chunk_id"]]
                        if chunk_ids:
                            safe_ids = [_escape_sql_literal(cid) for cid in chunk_ids]
                            quoted_ids = ", ".join(f"'{cid}'" for cid in safe_ids)
                            try:
                                self._table.delete(f"chunk_id IN ({quoted_ids})")
                            except Exception:
                                pass
                        self._table.add(records)
            except Exception as err:
                logger.error("Failed to persist chunks to LanceDB: %s. Chunks stored in fallback.", err)
        else:
            self._save_fallback_store()

        return len(raw_chunks)

    def add_vector(self, vector: list[float], document: dict[str, Any]) -> None:
        """Compatibility method matching VectorIndex.add_vector interface."""
        self.index_chunks([document], embeddings=[vector])

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks associated with doc_id from persistent and fallback storage."""
        # Remove from fallback store
        indices_to_remove = [i for i, d in enumerate(self._fallback_store.documents) if d.get("doc_id") == doc_id]
        for idx in reversed(indices_to_remove):
            del self._fallback_store.documents[idx]
            del self._fallback_store.vectors[idx]

        # Remove from LanceDB
        if self._has_lancedb and self._table is not None:
            try:
                safe_doc_id = _escape_sql_literal(doc_id)
                self._table.delete(f"doc_id = '{safe_doc_id}'")
                logger.info("Deleted chunks for doc_id=%s from LanceDB.", doc_id)
            except Exception as err:
                logger.error("Failed to delete doc_id=%s from LanceDB: %s", doc_id, err)
        else:
            self._save_fallback_store()

    def search_dense(self, query_vector: list[float], k: int = 5) -> list[dict[str, Any]]:
        """Perform nearest-neighbor vector search using cosine similarity.

        Args:
            query_vector: Dense embedding vector for the query.
            k: Maximum number of top candidates to return.

        Returns:
            List of matching chunk dictionaries with 'score' key (higher is more similar).
        """
        if k <= 0:
            return []

        if self._has_lancedb and self._table is not None:
            try:
                results = self._table.search(query_vector).limit(k).to_list()
                formatted_results: list[dict[str, Any]] = []
                for row in results:
                    r = dict(row)
                    dist = float(r.get("_distance", 1.0))
                    # Cosine distance: score = 1.0 - dist
                    r["score"] = max(0.0, 1.0 - dist)
                    formatted_results.append(r)
                return formatted_results
            except Exception as err:
                logger.warning("LanceDB vector search failed: %s. Falling back to in-memory search.", err)

        # Fallback in-memory search
        try:
            raw_results = self._fallback_store.search(query_vector, k=k)
            formatted: list[dict[str, Any]] = []
            for doc, dist in raw_results:
                d = dict(doc)
                d["score"] = max(0.0, 1.0 - float(dist))
                formatted.append(d)
            return formatted
        except Exception as err:
            logger.warning("Fallback search error: %s", err)
            return []

    def create_fts_index(self) -> None:
        """Create full-text search index on 'content' column in LanceDB if supported."""
        if self._has_lancedb and self._table is not None:
            try:
                if hasattr(self._table, "create_fts_index"):
                    self._table.create_fts_index("content", replace=True)
                    logger.info("Created LanceDB full-text search index on 'content'.")
            except Exception as err:
                logger.debug("LanceDB create_fts_index notice: %s", err)

    def _bm25_search_fallback(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Pure-Python BM25 keyword search across stored chunks (RETR-03)."""
        query_terms = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
        if not query_terms:
            return []

        docs = self._fallback_store.documents
        if not docs and self._has_lancedb and self._table is not None:
            try:
                table_rows = self._table.search().limit(10000).to_list()
                docs = [dict(r) for r in table_rows]
            except Exception as err:
                logger.debug("Could not read docs from LanceDB for BM25 fallback: %s", err)
                docs = []

        if not docs:
            return []

        k1 = 1.5
        b = 0.75
        N = len(docs)
        doc_tokens = []
        doc_lens = []

        for d in docs:
            raw_content = d.get("content", "")
            content_str = raw_content if isinstance(raw_content, str) else str(raw_content or "")
            toks = [w.lower() for w in re.findall(r"\w+", content_str)]
            doc_tokens.append(toks)
            doc_lens.append(len(toks))

        avg_dl = sum(doc_lens) / N if N > 0 else 1.0

        # Precompute document frequencies once for all query terms (O(N * |Q|) vs O(N^2 * |Q|))
        df_map: dict[str, int] = {}
        for qt in query_terms:
            df_map[qt] = sum(1 for dtoks in doc_tokens if qt in dtoks)

        scores: list[tuple[float, dict[str, Any]]] = []
        for doc, tokens, dl in zip(docs, doc_tokens, doc_lens):
            token_counts: dict[str, int] = {}
            for t in tokens:
                token_counts[t] = token_counts.get(t, 0) + 1

            doc_score = 0.0
            for qt in query_terms:
                if qt in token_counts:
                    tf = token_counts[qt]
                    df = df_map[qt]
                    idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
                    denom = tf + k1 * (1 - b + b * (dl / (avg_dl or 1.0)))
                    term_score = idf * ((tf * (k1 + 1)) / (denom or 1.0))
                    doc_score += term_score

            if doc_score > 0.0:
                d_copy = dict(doc)
                d_copy["score"] = float(doc_score)
                scores.append((doc_score, d_copy))

        scores.sort(key=lambda x: x[0], reverse=True)
        return [d for _, d in scores[:k]]

    def search_fts(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Perform full-text keyword search across indexed chunks.

        Args:
            query: Natural language query or exact keyword search term.
            k: Maximum number of top candidates to return.

        Returns:
            List of matching chunk dictionaries with 'score' key.
        """
        if k <= 0 or not query.strip():
            return []

        if self._has_lancedb and self._table is not None:
            try:
                results = self._table.search(query, query_type="fts").limit(k).to_list()
                formatted_results: list[dict[str, Any]] = []
                for row in results:
                    r = dict(row)
                    score = float(r.get("_score", r.get("score", 1.0)))
                    r["score"] = score
                    formatted_results.append(r)
                if formatted_results:
                    return formatted_results
            except Exception as err:
                logger.debug("LanceDB FTS search notice: %s. Using BM25 fallback.", err)

        return self._bm25_search_fallback(query, k=k)

    def search_hybrid(
        self,
        query: str,
        k: int = 5,
        k_rrf: int = DEFAULT_RRF_K,
    ) -> RetrievalResult:
        """Execute hybrid search combining dense semantic and BM25 full-text search with RRF.

        Args:
            query: Natural language query or question.
            k: Number of top evidence snippets to return.
            k_rrf: Reciprocal rank fusion smoothing parameter (default: 60).

        Returns:
            Canonical immutable RetrievalResult containing ranked EvidenceSnippet items (RETR-03, RETR-04).
        """
        if k <= 0 or not query.strip():
            return RetrievalResult(
                query=query,
                snippets=[],
                total_candidates=0,
                search_mode="hybrid",
            )

        candidate_pool = max(k * 2, 10)

        # 1. Dense vector search
        dense_matches: list[dict[str, Any]] = []
        if self.embedding_fn is not None:
            try:
                q_vec = self.embedding_fn(query)
                dense_matches = self.search_dense(q_vec, k=candidate_pool)
            except Exception as err:
                logger.warning("Dense search failed during hybrid retrieval: %s", err)

        # 2. Full-text search
        fts_matches = self.search_fts(query, k=candidate_pool)

        # Build chunks lookup
        chunks_map: dict[str, dict[str, Any]] = {}
        for d in dense_matches:
            cid = d.get("chunk_id")
            if cid:
                chunks_map[cid] = d
        for d in fts_matches:
            cid = d.get("chunk_id")
            if cid and cid not in chunks_map:
                chunks_map[cid] = d

        dense_ranks = [
            (d["chunk_id"], rank, float(d.get("score", 0.0)))
            for rank, d in enumerate(dense_matches, start=1)
            if d.get("chunk_id")
        ]
        fts_ranks = [
            (d["chunk_id"], rank, float(d.get("score", 0.0)))
            for rank, d in enumerate(fts_matches, start=1)
            if d.get("chunk_id")
        ]

        if dense_matches and fts_matches:
            search_mode: Any = "hybrid"
        elif dense_matches:
            search_mode = "dense"
        elif fts_matches:
            search_mode = "fts"
        else:
            search_mode = "fallback"

        rrf_fused = compute_rrf(dense_ranks, fts_ranks, k_rrf=k_rrf)
        top_candidates = rrf_fused[:k]

        snippets: list[EvidenceSnippet] = []
        for chunk_id, rrf_score, final_rank, d_rank, f_rank in top_candidates:
            raw = chunks_map.get(chunk_id, {})
            bbox = raw.get("bbox")
            bbox_json = raw.get("bbox_json")
            if bbox is None and bbox_json:
                try:
                    bbox = BBox.model_validate_json(bbox_json)
                except Exception:
                    pass

            snippet = EvidenceSnippet(
                content=str(raw.get("content", "")),
                doc_id=str(raw.get("doc_id", "doc_default")),
                filename=str(raw.get("filename", "")),
                page=int(raw.get("page", 1)),
                chunk_id=chunk_id,
                score=float(rrf_score),
                rank=final_rank,
                dense_rank=d_rank,
                fts_rank=f_rank,
                extraction=str(raw.get("extraction", "docling")),
                char_start=raw.get("char_start"),
                char_end=raw.get("char_end"),
                bbox=bbox,
            )
            snippets.append(snippet)

        return RetrievalResult(
            query=query,
            snippets=snippets,
            total_candidates=len(chunks_map),
            search_mode=search_mode,
        )

    def search(self, question: str, k: int = 3) -> list[tuple[dict[str, Any], float]]:
        """Legacy-compatible search facade returning (doc_dict, score) tuples."""
        warnings.warn(
            "HybridRetriever.search() is deprecated, use search_hybrid() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        result = self.search_hybrid(question, k=k)
        return [(s.model_dump(), s.score) for s in result.snippets]

    def get_context(self, question: str, k: int = 3) -> str:
        """Legacy-compatible context facade returning formatted evidence."""
        warnings.warn(
            "HybridRetriever.get_context() is deprecated, use search_hybrid() and RetrievalResult.formatted_evidence() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        result = self.search_hybrid(question, k=k)
        return result.formatted_evidence()
