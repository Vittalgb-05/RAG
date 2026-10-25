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
import shutil
from typing import Any
import warnings

from core.models import BBox, Chunk, EvidenceElement, EvidenceSnippet, RetrievalResult
from retrieval.vector_index import VectorIndex
import contextlib

logger = logging.getLogger(__name__)

# Optional LanceDB import
try:
    import lancedb
    import pyarrow as pa

    # Explicit schema prevents PyArrow from inferring nullable columns as `null` type
    # when the first batch contains only None values for char_start/char_end/bbox_json.
    def _build_chunks_schema(vector_dim: int = 384) -> "pa.Schema":
        return pa.schema(
            [
                pa.field("chunk_id", pa.string(), nullable=False),
                pa.field("doc_id", pa.string(), nullable=False),
                pa.field("filename", pa.string(), nullable=False),
                pa.field("page", pa.int64(), nullable=False),
                pa.field("content", pa.string(), nullable=False),
                pa.field("vector", pa.list_(pa.float32(), vector_dim), nullable=False),
                pa.field("extraction", pa.string(), nullable=False),
                pa.field("char_start", pa.int64(), nullable=True),
                pa.field("char_end", pa.int64(), nullable=True),
                pa.field("bbox_json", pa.string(), nullable=True),
            ]
        )

except ImportError:
    lancedb = None  # type: ignore[assignment]
    pa = None  # type: ignore[assignment]

    def _build_chunks_schema(vector_dim: int = 384):  # type: ignore[misc]
        return None


def _escape_sql_literal(value: str) -> str:
    """Escape single quotes in string literals for LanceDB SQL filter clauses (CR-03)."""
    return str(value).replace("'", "''")


def _doc_filter_clause(doc_id: str | list[str]) -> str:
    """Build a safe LanceDB SQL predicate restricting rows to the given document IDs."""
    allowed = {doc_id} if isinstance(doc_id, str) else set(doc_id)
    quoted = ", ".join(f"'{_escape_sql_literal(d)}'" for d in sorted(allowed))
    return f"doc_id IN ({quoted})"


# Canonical index location: <repo_root>/data/lancedb.  Older revisions resolved
# this relative to the package directory (retrieval/data/lancedb), which split the
# index from SQLite and made persisted vectors invisible after restart.
DEFAULT_DB_URI = Path(__file__).resolve().parent.parent / "data" / "lancedb"
LEGACY_DB_URI = Path(__file__).resolve().parent / "data" / "lancedb"
DEFAULT_RRF_K = 60


class VectorIndexError(RuntimeError):
    """Raised when vectors could not be written to the active persistent backend.

    Callers must treat this as a failed ingestion/re-index rather than a success,
    otherwise the SQLite catalog reports documents as indexed while they are not
    retrievable (silent vector loss).
    """


def _migrate_legacy_index(target: Path, legacy: Path | None = None) -> bool:
    """Copy a pre-0.2 index from the legacy package-relative location.

    The copy is non-destructive: the legacy directory is left untouched so a
    failed copy cannot lose the only existing vectors.  Only performed when the
    target has no table data yet.

    Args:
        target: Canonical LanceDB directory (``<repo_root>/data/lancedb``).
        legacy: Legacy package-relative directory (``retrieval/data/lancedb``).

    Returns:
        True if a migration copy was performed.
    """
    legacy = LEGACY_DB_URI if legacy is None else legacy
    if target.resolve() == legacy.resolve() or not legacy.exists():
        return False
    if any(target.glob("*.lance")):
        return False
    legacy_files = [p for p in legacy.rglob("*") if p.is_file()]
    if not legacy_files:
        return False

    try:
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy, target, dirs_exist_ok=True)
        logger.warning(
            "Migrated legacy LanceDB index from %s to %s (source left intact).",
            legacy,
            target,
        )
        return True
    except OSError as err:
        logger.error("Failed to migrate legacy LanceDB index from %s: %s", legacy, err)
        return False


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
        using_default_uri = db_uri is None
        self.db_uri = Path(db_uri) if db_uri is not None else DEFAULT_DB_URI
        if using_default_uri:
            _migrate_legacy_index(self.db_uri)
        self.embedding_fn = embedding_fn
        self.vector_dim = vector_dim

        self._has_lancedb = lancedb is not None
        self._db: Any = None
        self._table: Any = None

        # Pure-Python fallback store. It is loaded from the durable mirror only
        # when LanceDB is unavailable or a query actually falls through to the
        # fallback path, so a healthy LanceDB session does not hold a duplicate
        # copy of every vector in RAM.
        self._fallback_store = VectorIndex(
            distance_metric="cosine",
            embedding_fn=self.embedding_fn,
        )
        self._fallback_loaded = False
        self._fallback_file = self.db_uri / "fallback_store.json"

        # Keyword-search health (surfaced to Settings via fts_status()).
        self.fts_available: bool | None = None
        self.fts_last_error: str | None = None
        self._fts_warning_logged = False

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
        """Load the durable fallback mirror into memory (idempotent, lazy).

        Loading is deferred until LanceDB is unavailable or a query falls
        through to the fallback path, so a healthy LanceDB session never holds
        a second copy of every embedding. The mirror file is *never* cleared
        here; writes go through :meth:`_mirror_upsert`.
        """
        if self._fallback_loaded:
            return
        self._fallback_loaded = True
        if not self._fallback_file.exists():
            return
        try:
            docs, vectors = self._read_mirror()
            self._fallback_store = VectorIndex(
                distance_metric="cosine",
                embedding_fn=self.embedding_fn,
            )
            for doc, vec in zip(docs, vectors, strict=True):
                self._fallback_store.add_vector(vec, doc)
            logger.info("Loaded %d chunks from fallback persistent store at %s", len(docs), self._fallback_file)
        except Exception as err:
            logger.warning("Failed to load fallback store: %s", err)

    def _read_mirror(self) -> tuple[list[dict[str, Any]], list[list[float]]]:
        """Read raw documents/vectors from the durable mirror file."""
        if not self._fallback_file.exists():
            return [], []
        try:
            with open(self._fallback_file, encoding="utf-8") as f:
                data = json.load(f)
            docs = data.get("documents", []) or []
            vectors = data.get("vectors", []) or []
            # Keep the two lists aligned even if a previous write was truncated.
            usable = min(len(docs), len(vectors))
            return [dict(d) for d in docs[:usable]], [list(v) for v in vectors[:usable]]
        except Exception as err:
            logger.warning("Failed to read fallback store %s: %s", self._fallback_file, err)
            return [], []

    @staticmethod
    def _serialize_document(doc: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON-safe copy of a chunk document."""
        doc_copy = dict(doc)
        bbox = doc_copy.get("bbox")
        if isinstance(bbox, BBox) or hasattr(bbox, "model_dump"):
            doc_copy["bbox"] = bbox.model_dump()
        return doc_copy

    def _write_mirror(self, docs: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        """Atomically write the durable fallback mirror."""
        try:
            self.db_uri.mkdir(parents=True, exist_ok=True)
            serializable_docs = [self._serialize_document(d) for d in docs]
            serializable_vectors = [[float(x) for x in vec] for vec in vectors]
            tmp_path = self._fallback_file.with_name(self._fallback_file.name + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"documents": serializable_docs, "vectors": serializable_vectors}, f)
            tmp_path.replace(self._fallback_file)
        except Exception as err:
            logger.warning("Failed to save fallback store: %s", err)

    def _save_fallback_store(self) -> None:
        """Persist the in-memory fallback store (only when it is loaded)."""
        if not self._fallback_loaded:
            return
        self._write_mirror(self._fallback_store.documents, self._fallback_store.vectors)

    def _fallback_upsert(self, docs: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        """Merge documents into the in-memory fallback store by chunk_id."""
        existing_indices = {
            d.get("chunk_id"): i for i, d in enumerate(self._fallback_store.documents) if d.get("chunk_id")
        }
        for doc, emb in zip(docs, vectors, strict=True):
            cid = doc.get("chunk_id")
            if cid and cid in existing_indices:
                idx = existing_indices[cid]
                self._fallback_store.documents[idx] = doc
                self._fallback_store.vectors[idx] = emb
            else:
                self._fallback_store.add_vector(emb, doc)
                if cid:
                    existing_indices[cid] = len(self._fallback_store.documents) - 1

    def _mirror_upsert(self, docs: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        """Write-through merge new chunks into the durable mirror.

        While LanceDB is healthy the mirror is updated on disk only, so no
        duplicate vectors are retained in RAM. The merge is keyed by
        ``chunk_id``: re-indexing replaces rows in place and new documents are
        appended, so a later session's chunks never truncate the durable
        mirror. Merging keyed by ``doc_id`` instead would drop a document's
        text chunks when visual evidence is indexed in a second call for the
        same document. Document removal is handled explicitly by
        :meth:`delete_document`.

        Tradeoff: the mirror is a single JSON file, so each ingestion
        transaction reads and rewrites it (O(N) I/O). That keeps recovery
        simple and crash-safe while avoiding in-RAM duplication; a per-document
        file layout would avoid the rewrite at the cost of extra moving parts.
        """
        if self._fallback_loaded:
            self._fallback_upsert(docs, vectors)
            self._save_fallback_store()
            return

        existing_docs, existing_vectors = self._read_mirror()
        new_chunk_ids = {d.get("chunk_id") for d in docs if d.get("chunk_id")}
        merged_docs: list[dict[str, Any]] = []
        merged_vectors: list[list[float]] = []
        for doc, vec in zip(existing_docs, existing_vectors, strict=True):
            cid = doc.get("chunk_id")
            if cid and cid in new_chunk_ids:
                continue
            merged_docs.append(doc)
            merged_vectors.append(vec)
        for doc, vec in zip(docs, vectors, strict=True):
            merged_docs.append(self._serialize_document(doc))
            merged_vectors.append([float(x) for x in vec])
        self._write_mirror(merged_docs, merged_vectors)

    def _mirror_delete_document(self, doc_id: str) -> None:
        """Remove every chunk for ``doc_id`` from the durable mirror."""
        if self._fallback_loaded:
            indices = [i for i, d in enumerate(self._fallback_store.documents) if d.get("doc_id") == doc_id]
            for idx in reversed(indices):
                del self._fallback_store.documents[idx]
                del self._fallback_store.vectors[idx]
            self._save_fallback_store()
            return

        if not self._fallback_file.exists():
            return
        existing_docs, existing_vectors = self._read_mirror()
        kept = [
            (doc, vec) for doc, vec in zip(existing_docs, existing_vectors, strict=True) if doc.get("doc_id") != doc_id
        ]
        self._write_mirror([doc for doc, _ in kept], [vec for _, vec in kept])

    def set_embedding_fn(self, embedding_fn: Callable[[str], list[float]]) -> None:
        """Set or update the embedding function used for query vectorization."""
        self.embedding_fn = embedding_fn
        if hasattr(self._fallback_store, "_embedding_fn"):
            self._fallback_store._embedding_fn = embedding_fn

    def close(self) -> None:
        """Flush fallback persistence and release database handles."""
        if self._fallback_loaded:
            self._save_fallback_store()
        self._table = None
        self._db = None

    def __enter__(self) -> "HybridRetriever":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

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
        self._load_fallback_store()
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
        self._load_fallback_store()
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
                logger.error("Error dropping LanceDB 'chunks' table: %s", err)
                raise VectorIndexError(f"Failed to drop LanceDB table at {self.db_uri}: {err}") from err
            self._table = None

        self._fallback_store = VectorIndex(
            distance_metric="cosine",
            embedding_fn=self.embedding_fn,
        )
        self._fallback_loaded = True
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

        # 1. Persist to the active backend (LanceDB when healthy).
        if self._has_lancedb and self._db is not None:
            records: list[dict[str, Any]] = []
            for doc, emb in zip(raw_chunks, computed_embeddings, strict=True):
                bbox = doc.get("bbox")
                bbox_json = doc.get("bbox_json")
                if bbox_json is None and bbox is not None:
                    if hasattr(bbox, "model_dump_json"):
                        bbox_json = bbox.model_dump_json()
                    elif isinstance(bbox, dict):
                        bbox_json = json.dumps(bbox)

                # Coerce nullable int fields — keep None as None (not a string)
                char_start = doc.get("char_start")
                char_end = doc.get("char_end")
                if char_start is not None:
                    try:
                        char_start = int(char_start)
                    except (TypeError, ValueError):
                        char_start = None
                if char_end is not None:
                    try:
                        char_end = int(char_end)
                    except (TypeError, ValueError):
                        char_end = None

                records.append(
                    {
                        "chunk_id": str(doc.get("chunk_id", "")),
                        "doc_id": str(doc.get("doc_id", "")),
                        "filename": str(doc.get("filename", "")),
                        "page": int(doc.get("page", 1)),
                        "content": str(doc.get("content", "")),
                        "vector": [float(v) for v in emb],
                        "extraction": str(doc.get("extraction", "docling")),
                        "char_start": char_start,
                        "char_end": char_end,
                        "bbox_json": bbox_json if bbox_json is None else str(bbox_json),
                    }
                )

            try:
                if self._table is None:
                    # Create new table with an explicit schema so nullable columns
                    # (char_start, char_end, bbox_json) are typed correctly even when
                    # the first batch contains only None values for those fields.
                    schema = _build_chunks_schema(self.vector_dim)
                    if schema is not None:
                        pa_table = pa.Table.from_pylist(records, schema=schema)
                        self._table = self._db.create_table("chunks", data=pa_table, mode="create")
                    else:
                        self._table = self._db.create_table("chunks", data=records, mode="create")
                    logger.info("Created new LanceDB 'chunks' table with %d records.", len(records))
                    try:
                        self.create_fts_index()
                    except Exception as fts_err:
                        logger.debug("Initial FTS index creation notice: %s", fts_err)
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
                            with contextlib.suppress(Exception):
                                self._table.delete(f"chunk_id IN ({quoted_ids})")
                        self._table.add(records)
                    try:
                        self.create_fts_index()
                    except Exception as fts_err:
                        logger.debug("FTS index refresh notice: %s", fts_err)
            except Exception as err:
                # Keep a durable fallback copy for recovery, but never report success:
                # the caller must surface a failed ingestion instead of a document that
                # claims to be indexed while its vectors are absent.
                logger.error("Failed to persist chunks to LanceDB: %s", err)
                self._mirror_upsert(raw_chunks, computed_embeddings)
                raise VectorIndexError(
                    f"Failed to persist {len(raw_chunks)} chunks to LanceDB at {self.db_uri}: {err}"
                ) from err

        # 2. Write-through the durable fallback mirror. While LanceDB is healthy
        # this updates disk only (no duplicate in-RAM vectors); a later session
        # without LanceDB can still serve every document.
        self._mirror_upsert(raw_chunks, computed_embeddings)

        return len(raw_chunks)

    def index_evidence_elements(
        self,
        elements: list[EvidenceElement],
        filename: str | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """Convert and index visual evidence elements (figures, tables, charts) as searchable chunks."""
        if not elements:
            return 0
        chunks: list[dict[str, Any]] = []
        for idx, el in enumerate(elements):
            if not el.content or not el.content.strip():
                continue
            # Never index failed or placeholder analyses as factual evidence
            if el.content.startswith("[Visual element:"):
                continue
            chunk_dict = {
                "chunk_id": el.element_id or f"{el.doc_id}_fig_{el.page}_{idx:02d}",
                "doc_id": el.doc_id,
                "filename": filename or el.doc_id,
                "page": el.page,
                "content": f"[{el.kind.title()} on page {el.page}]: {el.content.strip()}",
                "char_start": 0,
                "char_end": len(el.content.strip()),
                "extraction": "vlm",
                "bbox": el.bbox.model_dump() if el.bbox else None,
            }
            chunks.append(chunk_dict)
        if chunks:
            return self.index_chunks(chunks, embeddings=embeddings)
        return 0

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks associated with doc_id from persistent and fallback storage."""
        # Remove from LanceDB first: if this fails, abort without mutating the
        # in-memory mirror so the fallback and persistent views stay consistent.
        if self._has_lancedb and self._db is not None:
            if self._table is None:
                self._init_table()
            if self._table is not None:
                try:
                    safe_doc_id = _escape_sql_literal(doc_id)
                    self._table.delete(f"doc_id = '{safe_doc_id}'")
                    logger.info("Deleted chunks for doc_id=%s from LanceDB.", doc_id)
                except Exception as err:
                    logger.error("Failed to delete doc_id=%s from LanceDB: %s", doc_id, err)
                    raise VectorIndexError(f"Failed to delete vectors for {doc_id} from {self.db_uri}: {err}") from err

        # Remove from the durable mirror (and the in-memory copy if loaded).
        # Otherwise a stale on-disk JSON can resurrect deleted documents the next
        # time LanceDB is unavailable.
        self._mirror_delete_document(doc_id)

    def fetch_document_chunks(self, doc_id: str, limit: int = 500) -> RetrievalResult:
        """Return every indexed chunk for a document in page order.

        Whole-document questions (e.g. "What are the questions?") must not be
        answered from a similarity-ranked sample, which silently omits later
        pages. This provides a deterministic, page-ordered inventory that callers
        can budget down while preserving page coverage.

        Args:
            doc_id: Document identifier to scope the read.
            limit: Safety ceiling on rows read from the backend.

        Returns:
            RetrievalResult with page-ordered snippets ranked from 1, or empty.
        """
        if not doc_id or limit <= 0:
            return RetrievalResult(query="", snippets=[], total_candidates=0, search_mode="document")

        rows: dict[str, dict[str, Any]] = {}

        if self._has_lancedb and self._table is not None:
            try:
                safe_doc_id = _escape_sql_literal(doc_id)
                raw_rows = self._table.search().where(f"doc_id = '{safe_doc_id}'").limit(limit).to_list()
                for row in raw_rows:
                    record = dict(row)
                    chunk_id = record.get("chunk_id")
                    if chunk_id:
                        rows[str(chunk_id)] = record
            except Exception as err:
                logger.warning("LanceDB whole-document read failed for %s: %s", doc_id, err)

        if not rows:
            self._load_fallback_store()
            for document in self._fallback_store.documents:
                if document.get("doc_id") != doc_id:
                    continue
                chunk_id = document.get("chunk_id")
                if chunk_id:
                    rows[str(chunk_id)] = dict(document)

        ordered = sorted(
            rows.values(),
            key=lambda record: (int(record.get("page", 1)), str(record.get("chunk_id", ""))),
        )
        snippets: list[EvidenceSnippet] = []
        for rank, raw in enumerate(ordered, start=1):
            bbox = raw.get("bbox")
            bbox_json = raw.get("bbox_json")
            if bbox is None and bbox_json:
                with contextlib.suppress(Exception):
                    bbox = BBox.model_validate_json(bbox_json)
            snippets.append(
                EvidenceSnippet(
                    content=str(raw.get("content", "")),
                    doc_id=str(raw.get("doc_id", doc_id)),
                    filename=str(raw.get("filename", "")),
                    page=int(raw.get("page", 1)),
                    chunk_id=str(raw.get("chunk_id", f"{doc_id}_{rank}")),
                    score=0.0,
                    rank=rank,
                    extraction=str(raw.get("extraction", "docling")),
                    char_start=raw.get("char_start"),
                    char_end=raw.get("char_end"),
                    bbox=bbox,
                )
            )

        cap_reached = len(rows) >= limit
        return RetrievalResult(
            query="",
            snippets=snippets,
            total_candidates=len(rows),
            search_mode="document_truncated" if cap_reached else "document",
            chunk_cap_reached=cap_reached,
        )

    def search_dense(
        self,
        query_vector: list[float],
        k: int = 5,
        doc_id: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform nearest-neighbor vector search using cosine similarity.

        Args:
            query_vector: Dense embedding vector for the query.
            k: Maximum number of top candidates to return.
            doc_id: Optional document ID or list of IDs to filter in the backend.

        Returns:
            List of matching chunk dictionaries with 'score' key (higher is more similar).
        """
        if k <= 0:
            return []

        if self._has_lancedb and self._table is not None:
            try:
                query_builder = self._table.search(query_vector)
                if hasattr(query_builder, "metric"):
                    with contextlib.suppress(Exception):
                        query_builder = query_builder.metric("cosine")
                if doc_id:
                    clause = _doc_filter_clause(doc_id)
                    if hasattr(query_builder, "where"):
                        query_builder = query_builder.where(clause)
                results = query_builder.limit(k).to_list()
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

        # Fallback in-memory search. Score the full store, then apply the
        # document scope before limiting to k — a hard candidate cap here would
        # silently drop documents whose chunks fall outside it.
        try:
            self._load_fallback_store()
            total = len(self._fallback_store.documents)
            if total == 0:
                return []
            raw_results = self._fallback_store.search(query_vector, k=total)
            formatted: list[dict[str, Any]] = []
            allowed = {doc_id} if isinstance(doc_id, str) else (set(doc_id) if doc_id else None)
            for doc, dist in raw_results:
                d = dict(doc)
                if allowed is not None and d.get("doc_id") not in allowed:
                    continue
                d["score"] = max(0.0, 1.0 - float(dist))
                formatted.append(d)
                if len(formatted) >= k:
                    break
            return formatted
        except Exception as err:
            logger.warning("Fallback search error: %s", err)
            return []

    def _set_fts_available(self) -> None:
        """Record that LanceDB full-text search is healthy."""
        self.fts_available = True
        self.fts_last_error = None

    def _set_fts_degraded(self, err: Exception) -> None:
        """Record a degraded FTS state and warn once per retriever instance."""
        self.fts_available = False
        self.fts_last_error = str(err)
        if not self._fts_warning_logged:
            logger.warning(
                "LanceDB full-text search unavailable; keyword search will use the in-Python BM25 fallback: %s",
                err,
            )
            self._fts_warning_logged = True
        else:
            logger.debug("LanceDB FTS still degraded: %s", err)

    def fts_status(self) -> dict[str, Any]:
        """Return keyword-search health for display in Settings.

        Returns:
            Dict with ``available`` (True/False/None when untested),
            ``degraded`` flag, ``last_error`` string, and active ``mode``.
        """
        if self.fts_available is True:
            mode = "lancedb-fts"
        elif self.fts_available is False:
            mode = "bm25-fallback"
        else:
            mode = "unknown"
        return {
            "available": self.fts_available,
            "degraded": self.fts_available is False,
            "last_error": self.fts_last_error,
            "mode": mode,
        }

    def create_fts_index(self) -> None:
        """Create full-text search index on 'content' column in LanceDB if supported."""
        if self._has_lancedb and self._table is not None:
            try:
                if hasattr(self._table, "create_fts_index"):
                    self._table.create_fts_index("content", replace=True)
                    self._set_fts_available()
                    logger.info("Created LanceDB full-text search index on 'content'.")
            except Exception as err:
                self._set_fts_degraded(err)

    def _bm25_candidate_docs(self, doc_id: str | list[str] | None = None) -> list[dict[str, Any]]:
        """Return every candidate document for BM25 scoring.

        Document scope is pushed into LanceDB before the row limit so a scoped
        search never truncates at a fixed global cap. Without LanceDB the
        complete durable mirror is scored.
        """
        if self._has_lancedb and self._table is not None:
            try:
                query_builder = self._table.search()
                if doc_id:
                    clause = _doc_filter_clause(doc_id)
                    if hasattr(query_builder, "where"):
                        query_builder = query_builder.where(clause)
                total = len(self._table)
                if total > 0:
                    return [dict(row) for row in query_builder.limit(total).to_list()]
            except Exception as err:
                logger.warning("Could not read LanceDB rows for BM25 fallback: %s", err)

        self._load_fallback_store()
        docs = self._fallback_store.documents
        if doc_id:
            allowed = {doc_id} if isinstance(doc_id, str) else set(doc_id)
            docs = [d for d in docs if d.get("doc_id") in allowed]
        return docs

    def _bm25_search_fallback(
        self,
        query: str,
        k: int = 5,
        doc_id: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Pure-Python BM25 keyword search across stored chunks (RETR-03)."""
        query_terms = [w.lower() for w in re.findall(r"\w+", query) if len(w) > 1]
        if not query_terms:
            return []

        docs = self._bm25_candidate_docs(doc_id)
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
        for doc, tokens, dl in zip(docs, doc_tokens, doc_lens, strict=True):
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

    def search_fts(
        self,
        query: str,
        k: int = 5,
        doc_id: str | list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Perform full-text keyword search across indexed chunks.

        Args:
            query: Natural language query or exact keyword search term.
            k: Maximum number of top candidates to return.
            doc_id: Optional document ID or list of IDs to filter in the backend.

        Returns:
            List of matching chunk dictionaries with 'score' key.
        """
        if k <= 0 or not query.strip():
            return []

        if self._has_lancedb and self._table is not None:
            try:
                query_builder = self._table.search(query, query_type="fts")
                if doc_id:
                    clause = _doc_filter_clause(doc_id)
                    if hasattr(query_builder, "where"):
                        query_builder = query_builder.where(clause)
                results = query_builder.limit(k).to_list()
                formatted_results: list[dict[str, Any]] = []
                for row in results:
                    r = dict(row)
                    score = float(r.get("_score", r.get("score", 1.0)))
                    r["score"] = score
                    formatted_results.append(r)
                self._set_fts_available()
                if formatted_results:
                    return formatted_results
            except Exception as err:
                self._set_fts_degraded(err)

        return self._bm25_search_fallback(query, k=k, doc_id=doc_id)

    def search_hybrid(
        self,
        query: str,
        k: int = 5,
        k_rrf: int = DEFAULT_RRF_K,
        doc_id: str | list[str] | None = None,
    ) -> RetrievalResult:
        """Execute hybrid search combining dense semantic and BM25 full-text search with RRF.

        Args:
            query: Natural language query or question.
            k: Number of top evidence snippets to return.
            k_rrf: Reciprocal rank fusion smoothing parameter (default: 60).
            doc_id: Optional document ID or list of document IDs to restrict retrieval to.

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

        candidate_pool = max(k * 5 if doc_id else k * 4, 30)

        # 1. Dense vector search (push document scope into the backend so the
        # selected document cannot be crowded out of a global top-K pool).
        dense_matches: list[dict[str, Any]] = []
        if self.embedding_fn is not None:
            try:
                q_vec = self.embedding_fn(query)
                dense_matches = self.search_dense(q_vec, k=candidate_pool, doc_id=doc_id)
            except Exception as err:
                logger.warning("Dense search failed during hybrid retrieval: %s", err)

        # 2. Full-text search
        fts_matches = self.search_fts(query, k=candidate_pool, doc_id=doc_id)

        # 3. Filter by doc_id again as defense-in-depth for backends that ignore
        # the pushed-down predicate.
        if doc_id:
            allowed_docs = {doc_id} if isinstance(doc_id, str) else set(doc_id)
            dense_matches = [d for d in dense_matches if d.get("doc_id") in allowed_docs]
            fts_matches = [d for d in fts_matches if d.get("doc_id") in allowed_docs]

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
                with contextlib.suppress(Exception):
                    bbox = BBox.model_validate_json(bbox_json)

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
