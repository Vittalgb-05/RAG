"""Persistent hybrid retrieval using LanceDB and CPU-pinned embeddings.

Provides serverless on-disk vector storage, full-text keyword indexing (BM25),
and Reciprocal Rank Fusion (RRF), with graceful in-memory fallback when LanceDB
is unavailable (RETR-01, RETR-02, RETR-03, RETR-04).
"""

from collections.abc import Callable
import logging
from pathlib import Path
from typing import Any

from models import Chunk
from vector_index import VectorIndex

logger = logging.getLogger(__name__)

# Optional LanceDB import
try:
    import lancedb
    import pyarrow as pa
except ImportError:
    lancedb = None  # type: ignore[assignment]
    pa = None  # type: ignore[assignment]


DEFAULT_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"


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
            import json

            with open(self._fallback_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            docs = data.get("documents", [])
            vecs = data.get("vectors", [])
            for doc, vec in zip(docs, vecs):
                self._fallback_store.add_vector(vec, doc)
            logger.info("Loaded %d chunks from fallback persistent store at %s", len(docs), self._fallback_file)
        except Exception as err:
            logger.warning("Failed to load fallback store: %s", err)

    def _save_fallback_store(self) -> None:
        """Persist fallback store to disk."""
        try:
            import json

            self.db_uri.mkdir(parents=True, exist_ok=True)
            with open(self._fallback_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "documents": self._fallback_store.documents,
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
                results = self._table.search().where(f"doc_id = '{doc_id}'").limit(1).to_list()
                return len(results) > 0
            except Exception:
                pass
        return any(d.get("doc_id") == doc_id for d in self._fallback_store.documents)

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

        # 1. Update in-memory fallback index
        for doc, emb in zip(raw_chunks, computed_embeddings):
            self._fallback_store.add_vector(emb, doc)

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
                        import json

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
                            quoted_ids = ", ".join(f"'{cid}'" for cid in chunk_ids)
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
                self._table.delete(f"doc_id = '{doc_id}'")
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
