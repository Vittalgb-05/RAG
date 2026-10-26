"""Hydration service to restore document records and retriever state on application launch."""

from collections.abc import Callable
import logging
import sqlite3

import streamlit as st

from core.doc_store import DocStore
from retrieval.hybrid_retriever import HybridRetriever
from retrieval.local_embedding import LocalEmbedding

logger = logging.getLogger(__name__)

# Callback signature: (completed, total, human-readable label).
ProgressCallback = Callable[[int, int, str], None]


def _report_progress(
    progress_callback: ProgressCallback | None,
    completed: int,
    total: int,
    label: str,
) -> None:
    """Invoke the optional progress reporter without letting UI errors abort hydration."""
    if progress_callback is None:
        return
    try:
        progress_callback(completed, total, label)
    except Exception as progress_err:  # pragma: no cover - UI boundary
        logger.debug("Hydration progress reporter failed: %s", progress_err)


def _consume_deletion_tombstones(doc_store: DocStore) -> bool:
    """Purge vectors for documents deleted while no retriever was available.

    Returns True when no tombstones remain. Failures keep the tombstone so the
    next startup retries instead of silently resurrecting deleted chunks.
    """
    try:
        tombstones = doc_store.list_deletion_tombstones()
    except (sqlite3.Error, OSError, ValueError) as err:
        logger.warning("Could not read deletion tombstones: %s", err, exc_info=True)
        return False

    if not tombstones:
        return True

    retriever = st.session_state.get("hybrid_retriever")
    owns_retriever = retriever is None
    remaining: list[str] = []
    try:
        if retriever is None:
            retriever = HybridRetriever()
        for doc_id in tombstones:
            try:
                retriever.delete_document(doc_id)
            except (OSError, RuntimeError, ValueError, TypeError) as err:
                logger.warning("Deferred vector purge failed for %s; will retry: %s", doc_id, err)
                remaining.append(doc_id)
                continue
            try:
                doc_store.clear_deletion_tombstone(doc_id)
            except (sqlite3.Error, OSError, ValueError) as err:
                logger.warning("Could not clear deletion tombstone for %s; will retry: %s", doc_id, err)
                remaining.append(doc_id)
        if remaining:
            logger.warning("Deferred vector cleanup incomplete for %d document(s).", len(remaining))
        else:
            logger.info("Purged deferred vectors for %d tombstoned document(s).", len(tombstones))
        return not remaining
    except (OSError, RuntimeError, ValueError, TypeError) as err:
        logger.warning("Could not initialize retriever for deferred vector cleanup: %s", err)
        return False
    finally:
        if owns_retriever and retriever is not None:
            try:
                retriever.close()
            except Exception as close_err:  # pragma: no cover - best-effort teardown
                logger.debug("Failed to close temporary retriever after tombstone cleanup: %s", close_err)


def hydrate_startup_state(doc_store: DocStore, progress_callback: ProgressCallback | None = None) -> None:
    """Hydrate session state from SQLite and LanceDB on initial browser connection.

    Ensures that documents indexed in previous sessions are immediately visible
    in the library and searchable in the retriever without requiring re-upload (CR-01).

    Only documents whose vectors are actually missing are re-embedded; a library
    whose vector index is fully valid performs no embedding work.  Hydration stays
    synchronous (background jobs are a deferred feature), but reports repair
    progress through ``progress_callback`` so the UI is not silently frozen.

    Args:
        doc_store: Persistent document store to read the catalog from.
        progress_callback: Optional callback receiving ``(completed, total, label)``
            while missing vectors are repaired.
    """
    if st.session_state.get("_startup_hydrated", False):
        return

    try:
        docs = doc_store.list_documents()
    except (sqlite3.Error, OSError, ValueError) as e:
        # Leave the flag unset so the next rerun can retry instead of permanently
        # presenting an empty library for the rest of the session.
        logger.warning("Could not query documents for hydration: %s", e, exc_info=True)
        return

    failed_docs = [d for d in docs if d.status == "failed"]
    for d in failed_docs:
        st.session_state.failed_doc_ids.add(d.doc_id)

    tombstones_cleared = _consume_deletion_tombstones(doc_store)

    indexed_docs = [d for d in docs if d.status == "indexed"]
    if not indexed_docs:
        st.session_state._startup_hydrated = tombstones_cleared
        return

    for doc in indexed_docs:
        st.session_state.doc_ids.add(doc.doc_id)
        st.session_state.indexed_files.add(doc.filename)
        st.session_state.document_metadata[doc.doc_id] = {
            "doc_id": doc.doc_id,
            "filename": doc.filename,
            "sha256": doc.sha256,
            "upload_time": doc.upload_time,
            "pages": doc.num_pages,
            "chunks": doc.num_chunks,
            "needs_reindex": False,
        }

    # Hydrate and verify hybrid retriever state against SQLite records
    retriever_ready = False
    try:
        if st.session_state.hybrid_retriever is None:
            retriever = HybridRetriever()
            if st.session_state.local_embedding is None:
                st.session_state.local_embedding = LocalEmbedding()
            retriever.embedding_fn = st.session_state.local_embedding._embed_one
            st.session_state.hybrid_retriever = retriever
        else:
            retriever = st.session_state.hybrid_retriever

        # Fast validity scan: only documents whose vectors are actually missing
        # are re-chunked and re-embedded.  This avoids re-embedding the entire
        # library on every cold start when the index is healthy.
        repair_docs = []
        for doc in indexed_docs:
            try:
                if retriever.has_document(doc.doc_id):
                    continue
            except Exception as check_err:
                logger.warning(
                    "Vector coverage check failed for %s: %s",
                    doc.doc_id,
                    check_err,
                    exc_info=True,
                )
            repair_docs.append(doc)

        if not repair_docs:
            logger.info(
                "Vector index valid for all %d indexed document(s); no re-embedding needed.",
                len(indexed_docs),
            )
            retriever_ready = True
        else:
            if st.session_state.local_embedding is None:
                st.session_state.local_embedding = LocalEmbedding()
                retriever.embedding_fn = st.session_state.local_embedding._embed_one

            total = len(repair_docs)
            logger.info("Repairing vectors for %d of %d indexed document(s).", total, len(indexed_docs))
            _report_progress(progress_callback, 0, total, f"Repairing vector index (0/{total})")

            for position, doc in enumerate(repair_docs, start=1):
                _report_progress(
                    progress_callback,
                    position - 1,
                    total,
                    f"Repairing {doc.filename} ({position}/{total})",
                )
                chunks = doc_store.get_chunks_for_doc(doc.doc_id)
                if not chunks:
                    logger.warning("Indexed document %s has no stored chunks; marking for re-index.", doc.doc_id)
                    st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = True
                else:
                    try:
                        logger.info("Auto-repairing missing vector index for %s (%s)", doc.filename, doc.doc_id)
                        embs = st.session_state.local_embedding.get_embeddings([c.content for c in chunks])
                        retriever.index_chunks([c.model_dump() for c in chunks], embeddings=embs.tolist())
                        if not retriever.has_document(doc.doc_id):
                            raise RuntimeError("repair write did not produce retrievable vectors")
                        st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = False
                    except Exception as repair_err:
                        # One corrupt document must not prevent the rest of the
                        # library from hydrating; surface the failure and flag it.
                        logger.error(
                            "Vector repair failed for %s: %s",
                            doc.doc_id,
                            repair_err,
                            exc_info=True,
                        )
                        st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = True

                _report_progress(
                    progress_callback,
                    position,
                    total,
                    f"Repairing vector index ({position}/{total})",
                )
            retriever_ready = True
    except Exception as err:
        logger.error("Retriever auto-hydration on startup failed: %s", err, exc_info=True)
    finally:
        # Mark hydrated only when retriever discovery/repair completed.  A hard
        # failure leaves the flag unset so the next rerun can retry.
        if retriever_ready and tombstones_cleared:
            st.session_state._startup_hydrated = True
