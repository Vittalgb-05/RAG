"""Document lifecycle service managing atomic deletion, purge, and reindexing."""

import logging
from pathlib import Path
import shutil
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

        # 1. SQLite deletion (chunks, pages, evidence, summaries, doc)
        deleted = self.doc_store.delete_document(doc_id)

        # 2. LanceDB deletion
        if self.retriever is not None:
            try:
                self.retriever.delete_document(doc_id)
            except Exception as err:
                logger.warning("LanceDB deletion notice for %s: %s", doc_id, err)

        # 3. Disk cache removal
        if sha256:
            try:
                c_dir = cache_dir_for(self.cache_dir, sha256)
                if c_dir.exists():
                    shutil.rmtree(c_dir, ignore_errors=True)
            except Exception as cache_err:
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
        """Completely purge all database records, vector tables, disk caches, and chat history."""
        # 1. SQLite purge with VACUUM
        self.doc_store.purge_all()

        # 2. LanceDB purge
        if self.retriever is not None:
            try:
                self.retriever.purge_all()
            except Exception as err:
                logger.warning("LanceDB purge notice: %s", err)

        # 3. Full disk cache removal
        try:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir, ignore_errors=True)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as cache_err:
            logger.warning("Disk cache purge notice: %s", cache_err)

        # 4. Session state cleansing
        if session_state is not None:
            if hasattr(session_state, "doc_ids"):
                session_state.doc_ids.clear()
            if hasattr(session_state, "failed_doc_ids"):
                session_state.failed_doc_ids.clear()
            if hasattr(session_state, "indexed_files"):
                session_state.indexed_files.clear()
            if hasattr(session_state, "document_metadata"):
                session_state.document_metadata.clear()
            if hasattr(session_state, "chat_history"):
                session_state.chat_history.clear()

            # Remove all cached summary keys
            for k in list(session_state.keys()):
                if k.startswith("summary_"):
                    del session_state[k]

            session_state.selected_chat_doc = None
            session_state.selected_summary_doc = None
            session_state.uploader_key = getattr(session_state, "uploader_key", 0) + 1
            session_state._startup_hydrated = False

        logger.info("Purged all stored data across SQLite, LanceDB, disk cache, and session state.")

    def reindex_document(self, doc_id: str) -> bool:
        """Rebuild vector embeddings in LanceDB from persisted SQLite chunks.

        Args:
            doc_id: Unique document ID.

        Returns:
            True if document was successfully reindexed, False otherwise.
        """
        chunks = self.doc_store.get_chunks_for_doc(doc_id)
        if not chunks or self.retriever is None:
            return False

        if self.embedding is None:
            self.embedding = LocalEmbedding()

        try:
            embs = self.embedding.get_embeddings([c.content for c in chunks])
            chunk_dicts = [c.model_dump() for c in chunks]
            self.retriever.index_chunks(chunk_dicts, embeddings=embs.tolist())

            # Also reindex any visual elements
            evidence = self.doc_store.get_evidence_for_doc(doc_id)
            if evidence:
                doc = self.doc_store.get_document(doc_id)
                fname = doc.filename if doc else doc_id
                self.retriever.index_evidence_elements(evidence, filename=fname)

            logger.info("Successfully reindexed %d chunks for doc_id=%s", len(chunks), doc_id)
            return True
        except Exception as err:
            logger.error("Failed to reindex document %s: %s", doc_id, err)
            return False
