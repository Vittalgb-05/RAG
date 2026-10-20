"""Hydration service to restore document records and retriever state on application launch."""

import logging
import streamlit as st

from doc_store import DocStore
from hybrid_retriever import HybridRetriever
from local_embedding import LocalEmbedding

logger = logging.getLogger(__name__)


def hydrate_startup_state(doc_store: DocStore) -> None:
    """Hydrate session state from SQLite and LanceDB on initial browser connection.

    Ensures that documents indexed in previous sessions are immediately visible
    in the library and searchable in the retriever without requiring re-upload (CR-01).
    """
    if st.session_state.get("_startup_hydrated", False):
        return

    st.session_state._startup_hydrated = True

    try:
        docs = doc_store.list_documents()
    except Exception as e:
        logger.warning("Could not query documents for hydration: %s", e)
        return

    failed_docs = [d for d in docs if d.status == "failed"]
    for d in failed_docs:
        st.session_state.failed_doc_ids.add(d.doc_id)

    indexed_docs = [d for d in docs if d.status == "indexed"]
    if not indexed_docs:
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
    try:
        if st.session_state.hybrid_retriever is None:
            retriever = HybridRetriever()
            if st.session_state.local_embedding is None:
                st.session_state.local_embedding = LocalEmbedding()
            retriever.embedding_fn = st.session_state.local_embedding._embed_one
            st.session_state.hybrid_retriever = retriever
        else:
            retriever = st.session_state.hybrid_retriever

        # Verify each document's presence in the vector store and repair if missing
        for doc in indexed_docs:
            if not retriever.has_document(doc.doc_id):
                chunks = doc_store.get_chunks_for_doc(doc.doc_id)
                if chunks:
                    logger.info("Auto-repairing missing vector index for %s (%s)", doc.filename, doc.doc_id)
                    embs = st.session_state.local_embedding.get_embeddings([c.content for c in chunks])
                    retriever.index_chunks([c.model_dump() for c in chunks], embeddings=embs.tolist())
                    st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = False
                else:
                    st.session_state.document_metadata[doc.doc_id]["needs_reindex"] = True
    except Exception as err:
        logger.warning("Retriever auto-hydration on startup failed: %s", err)
