"""Document lifecycle service managing atomic deletion, purge, and reindexing."""

from __future__ import annotations
import logging
from pathlib import Path
import shutil
import sqlite3

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding
from core.models import cache_dir_for

logger = logging.getLogger(__name__)


class LifecycleService:
    """Coordinates document lifecycle operations across storage tiers."""

    def __init__(
        self,
        doc_store: DocStore,
        retriever: HybridRetriever | None = None,
        hybrid_retriever: HybridRetriever | None = None,
        embedding: LocalEmbedding | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.doc_store = doc_store
        self.retriever = retriever if retriever is not None else hybrid_retriever
        self.hybrid_retriever = self.retriever
        self.embedding = embedding
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent.parent / ".cache")

    def delete_document(self, doc_id: str) -> bool:
        """Atomically delete a document across SQLite, LanceDB, and disk cache.

        Args:
            doc_id: Unique document ID.

        Returns:
            True if document was deleted from storage, False otherwise.
        """
        doc = self.doc_store.get_document(doc_id)
        sha256 = doc.sha256 if doc else ""
        filename = doc.filename if doc else ""

        # 1. Vector deletion first. If this fails we abort before touching SQLite.
        if self.retriever is not None:
            try:
                self.retriever.delete_document(doc_id)
            except Exception as err:
                logger.error("Vector deletion failed for %s; aborting delete: %s", doc_id, err, exc_info=True)
                raise
        else:
            logger.warning(
                "No vector retriever available; deleting %s from SQLite and recording "
                "a deferred vector-cleanup tombstone.",
                doc_id,
            )

        # 2. SQLite deletion (chunks, pages, evidence, summaries, doc)
        deleted = self.doc_store.delete_document(doc_id, record_tombstone=self.retriever is None)

        # 3. Disk cache removal (best effort)
        if sha256:
            try:
                c_dir = cache_dir_for(self.cache_dir, sha256)
                if c_dir.exists():
                    shutil.rmtree(c_dir)
            except OSError as cache_err:
                logger.warning("Cache deletion notice for %s: %s", doc_id, cache_err)

        logger.info("Successfully deleted document %s (%s)", doc_id, filename)
        return deleted

    def purge_all(self, session_state: Any = None) -> None:
        """Completely purge all database records, vector tables, disk caches, and chat history.

        Raises:
            RuntimeError: If any storage tier could not be purged.
        """
        failures: list[str] = []

        # 1. Vector store first
        if self.retriever is not None:
            try:
                self.retriever.purge_all()
            except Exception as err:
                logger.error("LanceDB purge failed: %s", err, exc_info=True)
                failures.append(f"vector index: {err}")
        else:
            logger.warning("No vector retriever available; purging SQLite and disk cache only.")

        # 2. SQLite purge with VACUUM (includes chat sessions and messages)
        try:
            self.doc_store.purge_all()
        except sqlite3.Error as err:
            logger.error("SQLite purge failed: %s", err, exc_info=True)
            failures.append(f"SQLite: {err}")

        # 3. Full disk cache removal
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as cache_err:
            logger.warning("Disk cache purge notice: %s", cache_err)
            failures.append(f"disk cache: {cache_err}")

        if session_state is not None:
            for key in ("doc_ids", "failed_doc_ids", "indexed_files"):
                if isinstance(session_state, dict):
                    session_state[key] = set()
                elif hasattr(session_state, key):
                    setattr(session_state, key, set())
            if isinstance(session_state, dict):
                session_state["document_metadata"] = {}
            elif hasattr(session_state, "document_metadata"):
                session_state.document_metadata = {}

        if failures:
            raise RuntimeError("Purge incomplete — " + "; ".join(failures))
        logger.info("Purged all stored data across SQLite, LanceDB, and disk cache.")

    def reindex_document(self, doc_id: str) -> bool:
        """Rebuild vector embeddings in LanceDB from persisted SQLite chunks.

        Args:
            doc_id: Unique document ID.

        Returns:
            True if document was successfully reindexed, False otherwise.
        """
        chunks = self.doc_store.get_chunks_for_doc(doc_id)
        if not chunks:
            logger.warning("Cannot reindex %s: no stored chunks.", doc_id)
            return False
        if self.retriever is None:
            logger.warning("Cannot reindex %s: no vector retriever available.", doc_id)
            return False

        if self.embedding is None:
            self.embedding = LocalEmbedding()

        try:
            # Mark indexing first (B14)
            self.doc_store.update_document_status(doc_id, "indexing")

            # Remove stale vectors first
            self.retriever.delete_document(doc_id)

            embs = self.embedding.get_embeddings([c.content for c in chunks])
            chunk_dicts = [c.model_dump() for c in chunks]
            self.retriever.index_chunks(chunk_dicts, embeddings=embs.tolist())

            # Also reindex any visual elements (B13)
            evidence = self.doc_store.get_evidence_for_doc(doc_id)
            if evidence:
                doc = self.doc_store.get_document(doc_id)
                fname = doc.filename if doc else doc_id
                self.retriever.index_evidence_elements(evidence, filename=fname)

            if not self.retriever.has_document(doc_id):
                logger.error("Reindex verification failed for doc_id=%s: no vectors found after write.", doc_id)
                self.doc_store.update_document_status(doc_id, "failed")
                return False

            self.doc_store.update_document_status(doc_id, "indexed")
            logger.info("Successfully reindexed %d chunks for doc_id=%s", len(chunks), doc_id)
            return True
        except (OSError, RuntimeError, ValueError) as err:
            logger.error("Failed to reindex document %s: %s", doc_id, err, exc_info=True)
            try:
                self.doc_store.update_document_status(doc_id, "failed")
            except Exception:
                pass
            return False
