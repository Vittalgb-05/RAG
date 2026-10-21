"""Shared reset routine for in-memory Streamlit session state.

Centralizes teardown of chat, retrieval, provider, and privacy state so the
sidebar "Clear Session" action and the Settings "Reset In-Memory Session" action
cannot drift apart. Both must drop prior evidence, credentials, and hydration
flags; a partial reset can leak retrieved document text into a new conversation.
"""

import streamlit as st


def reset_in_memory_session() -> None:
    """Reset all in-memory session state, models, and credentials."""
    st.session_state.doc_ids = set()
    st.session_state.failed_doc_ids = set()
    st.session_state.indexed_files = set()
    st.session_state.document_metadata = {}
    st.session_state.local_embedding = None

    ai_model = st.session_state.get("ai_model")
    if ai_model is not None and hasattr(ai_model, "reset_turn_state"):
        try:
            ai_model.reset_turn_state()
        except Exception:
            pass

    if st.session_state.get("hybrid_retriever"):
        try:
            st.session_state.hybrid_retriever.close()
        except Exception:
            pass
    st.session_state.hybrid_retriever = None
    st.session_state.chat_history = []
    st.session_state.uploader_key = st.session_state.get("uploader_key", 0) + 1
    st.session_state._startup_hydrated = False

    for key in list(st.session_state.keys()):
        if key.startswith("summary_"):
            del st.session_state[key]

    if st.session_state.get("active_cloud_provider"):
        try:
            st.session_state.active_cloud_provider.close()
        except Exception:
            pass
    st.session_state.active_cloud_provider = None
    st.session_state._cached_cloud_model = None
    st.session_state._cached_cloud_key = None
    st.session_state.cloud_mode = False
    st.session_state.cloud_mode_toggle = False
    st.session_state.settings_cloud_toggle = False
    st.session_state.user_consented = False
    st.session_state.selected_chat_doc = None
    st.session_state.selected_summary_doc = None
    st.session_state.cloud_api_keys = {"groq": "", "openai": "", "anthropic": ""}
