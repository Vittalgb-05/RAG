"""Document lifecycle service managing atomic deletion, purge, and reindexing."""

import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding
from core.models import cache_dir_for

logger = logging.getLogger(__name__)


class LifecycleService:
    """Coordinates document lifecycle operations across storage tiers and session state."""

    def __init__(
        self,
        doc_store: DocStore,
        hybrid_retriever: HybridRetriever | None = None,
        local_embedding: LocalEmbedding | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.doc_store = doc_store
        self.retriever = hybrid_retriever
        self.embedding = local_embedding
        self.cache_dir = cache_dir or (Path(__file__).resolve().parent.parent / ".cache")

    def delete_document(self, doc_id: str, session_state: Any = None) -> bool:
        """Atomically delete a document across SQLite, LanceDB, disk cache, and session state.

        Args:
            doc_id: Unique document ID.
            session_state: Optional Streamlit session_state dict-like object.

        Returns:
            True if document was deleted from storage, False otherwise.
        """
        doc = self.doc_store.get_document(doc_id)
        sha256 = doc.sha256 if doc else ""
        filename = doc.filename if doc else ""

        # 1. Vector deletion first.  If this fails we abort before touching SQLite so
        # the catalog and the index cannot disagree (a deleted document whose chunks
        # are still retrievable is worse than a visible, retryable failure).
        if self.retriever is not None:
            try:
                self.retriever.delete_document(doc_id)
            except Exception as err:
                # Re-raised: a partially deleted document is worse than a
                # visible, retryable failure, so never swallow this boundary.
                logger.error("Vector deletion failed for %s; aborting delete: %s", doc_id, err, exc_info=True)
                raise
        else:
            logger.warning(
                "No vector retriever available; deleting %s from SQLite only. "
                "Existing vectors may be resurrected by hydration.",
                doc_id,
            )

        # 2. SQLite deletion (chunks, pages, evidence, summaries, doc)
        deleted = self.doc_store.delete_document(doc_id)

        # 3. Disk cache removal (best-effort; a leftover cache cannot serve answers)
        if sha256:
            try:
                c_dir = cache_dir_for(self.cache_dir, sha256)
                if c_dir.exists():
                    shutil.rmtree(c_dir)
            except OSError as cache_err:
                # Best-effort artifact cleanup: a leftover cache cannot serve answers.
                logger.warning("Cache deletion notice for %s: %s", doc_id, cache_err)

        # 4. Session state synchronization
        if session_state is not None:
            if hasattr(session_state, "doc_ids"):
                session_state.doc_ids.discard(doc_id)
            if hasattr(session_state, "failed_doc_ids"):
                session_state.failed_doc_ids.discard(doc_id)
            if hasattr(session_state, "indexed_files") and filename:
                session_state.indexed_files.discard(filename)
            if hasattr(session_state, "document_metadata"):
                session_state.document_metadata.pop(doc_id, None)

            # Purge any session summary keys for this document
            prefix = f"summary_{doc_id}_"
            for k in list(session_state.keys()):
                if k.startswith(prefix):
                    del session_state[k]

            if getattr(session_state, "selected_chat_doc", None) == doc_id:
                session_state.selected_chat_doc = None
            if getattr(session_state, "selected_summary_doc", None) == doc_id:
                session_state.selected_summary_doc = None

        logger.info("Successfully deleted document %s (%s)", doc_id, filename)
        return deleted

    def purge_all(self, session_state: Any = None) -> None:
        """Completely purge all database records, vector tables, disk caches, and chat history.

        Raises:
            RuntimeError: If any storage tier could not be purged.  Session state is
                still cleansed so the UI never continues to display deleted content,
                but the failure is never hidden from the caller.
        """
        failures: list[str] = []

        # 1. Vector store first: if this fails, SQLite remains the source of truth
        # and hydration can restore vectors on the next launch.
        if self.retriever is not None:
            try:
                self.retriever.purge_all()
            except Exception as err:
                logger.error("LanceDB purge failed: %s", err, exc_info=True)
                failures.append(f"vector index: {err}")
        else:
            logger.warning("No vector retriever available; purging SQLite and disk cache only.")

        # 2. SQLite purge with VACUUM
        try:
            self.doc_store.purge_all()
        except sqlite3.Error as err:
            logger.error("SQLite purge failed: %s", err, exc_info=True)
            failures.append(f"SQLite: {err}")

        # 3. Full disk cache removal (best-effort artifact cleanup)
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as cache_err:
            logger.warning("Disk cache purge notice: %s", cache_err)
            failures.append(f"disk cache: {cache_err}")

        # 4. Session state cleansing
        if session_state is not None:
            for attr in ("doc_ids", "failed_doc_ids", "indexed_files", "document_metadata", "chat_history"):
                container = getattr(session_state, attr, None)
                if container is not None and hasattr(container, "clear"):
                    container.clear()

            # Remove all cached summary keys
            for k in list(session_state.keys()):
                if k.startswith("summary_"):
                    del session_state[k]

            session_state.selected_chat_doc = None
            session_state.selected_summary_doc = None
            session_state.uploader_key = (getattr(session_state, "uploader_key", 0) or 0) + 1
            session_state._startup_hydrated = False

        if failures:
            raise RuntimeError("Purge incomplete — " + "; ".join(failures))
        logger.info("Purged all stored data across SQLite, LanceDB, disk cache, and session state.")

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
            # Remove stale vectors first: if the chunk set shrank since the previous
            # index, upsert alone would leave orphaned chunk IDs retrievable.
            self.retriever.delete_document(doc_id)

            embs = self.embedding.get_embeddings([c.content for c in chunks])
            chunk_dicts = [c.model_dump() for c in chunks]
            self.retriever.index_chunks(chunk_dicts, embeddings=embs.tolist())

            # Also reindex any visual elements
            evidence = self.doc_store.get_evidence_for_doc(doc_id)
            if evidence:
                doc = self.doc_store.get_document(doc_id)
                fname = doc.filename if doc else doc_id
                self.retriever.index_evidence_elements(evidence, filename=fname)

            if not self.retriever.has_document(doc_id):
                logger.error("Reindex verification failed for doc_id=%s: no vectors found after write.", doc_id)
                return False

            logger.info("Successfully reindexed %d chunks for doc_id=%s", len(chunks), doc_id)
            return True
        except (OSError, RuntimeError, ValueError) as err:
            logger.error("Failed to reindex document %s: %s", doc_id, err, exc_info=True)
            return False
