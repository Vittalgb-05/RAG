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
        }

    # Hydrate hybrid retriever if chunks exist on disk
    if st.session_state.hybrid_retriever is None:
        try:
            retriever = HybridRetriever()
            if retriever.count_chunks() > 0:
                if st.session_state.local_embedding is None:
                    st.session_state.local_embedding = LocalEmbedding()
                retriever.embedding_fn = st.session_state.local_embedding._embed_one
                st.session_state.hybrid_retriever = retriever
            else:
                retriever.close()
        except Exception as err:
            logger.warning("Retriever auto-hydration on startup failed: %s", err)
