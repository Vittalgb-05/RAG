"""Chat session management and Server-Sent Event completion streaming."""

from __future__ import annotations
import datetime
import json
import threading
import time
import uuid
from typing import Any
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from api.container import AppContainer
from api.deps import get_container
from api.errors import ApiError, problem_from_exc
from api.schemas.chat import (
    ChatMessageResponse,
    ChatMessageUsage,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionUpdate,
    SendMessage,
)
from api.schemas.common import Grounding, Scope, Source
from api.streaming import Emit, SSE_HEADERS, sse_from_worker
from core.limits import MAX_CHAT_TURNS
from core.sanitizer import sanitize_markdown_for_local

router = APIRouter(tags=["chat"])

_ACTIVE_STOPS: dict[str, threading.Event] = {}
_STOPS_LOCK = threading.Lock()


def _get_document_metadata_map(c: AppContainer) -> dict[str, dict[str, Any]]:
    docs = c.doc_store.list_documents()
    res: dict[str, dict[str, Any]] = {}
    for d in docs:
        if d.status == "indexed":
            res[d.doc_id] = {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "sha256": d.sha256,
                "pages": d.num_pages,
                "chunks": d.num_chunks,
            }
    return res


def _format_sources(snippets: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "rank": s.rank,
            "doc_id": s.doc_id,
            "filename": s.filename,
            "page": s.page,
            "preview": s.content[:200],
            "score": getattr(s, "dense_score", None),
            "cited": False,
            "supported": None,
            "bbox": s.bbox.model_dump() if getattr(s, "bbox", None) else None,
        }
        for s in snippets
    ]


def _finish(
    emit: Emit,
    c: AppContainer,
    session_id: str,
    body: SendMessage,
    assistant_turn: dict[str, Any],
    ttft_ms: float = 0.0,
    duration_ms: float = 0.0,
) -> None:
    answer_text = assistant_turn.get("content", "")
    if not c.cloud.enabled:
        answer_text = sanitize_markdown_for_local(answer_text)

    # Calculate token count approximation
    token_count = max(1, len(answer_text) // 4)
    usage = {
        "ttft_ms": round(ttft_ms, 2),
        "tokens": token_count,
        "duration_ms": round(duration_ms, 2),
    }

    user_msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    asst_msg_id = f"msg_{uuid.uuid4().hex[:16]}"
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()

    grounding_data = assistant_turn.get("grounding_report") or {}
    sources_data = _format_sources(assistant_turn.get("snippets") or [])

    if c.settings.persist_chat:
        try:
            c.doc_store.append_chat_message(
                session_id=session_id,
                message_id=user_msg_id,
                role="user",
                content=body.content,
            )
            c.doc_store.append_chat_message(
                session_id=session_id,
                message_id=asst_msg_id,
                role="assistant",
                content=answer_text,
                grounding=grounding_data,
                sources=sources_data,
                usage=usage,
            )
        except Exception:
            pass

    emit(
        "final",
        {
            "message_id": asst_msg_id,
            "answer_markdown": answer_text,
            "grounding": grounding_data,
            "sources": sources_data,
            "usage": usage,
        },
    )


@router.get("/chat/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(c: AppContainer = Depends(get_container)) -> list[ChatSessionResponse]:
    """List all persisted chat sessions."""
    rows = c.doc_store.list_chat_sessions()
    sessions = []
    for r in rows:
        scope_dict = r.get("scope") or {"type": "all", "doc_ids": []}
        sessions.append(
            ChatSessionResponse(
                id=r["id"],
                title=r["title"],
                scope=Scope(**scope_dict),
                updated_at=r["updated_at"],
                messages=[],
            )
        )
    return sessions


@router.post("/chat/sessions", response_model=ChatSessionResponse)
async def create_session(
    body: ChatSessionCreate,
    c: AppContainer = Depends(get_container),
) -> ChatSessionResponse:
    """Create a new chat session."""
    session = c.doc_store.create_chat_session(title=body.title, scope=body.scope.model_dump())
    return ChatSessionResponse(
        id=session["id"],
        title=session["title"],
        scope=Scope(**session["scope"]),
        updated_at=session["updated_at"],
        messages=[],
    )


@router.get("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_session(session_id: str, c: AppContainer = Depends(get_container)) -> ChatSessionResponse:
    """Get chat session details and message history."""
    session = c.doc_store.get_chat_session(session_id)
    if not session:
        raise ApiError(status_code=404, code="not_found", detail=f"Chat session '{session_id}' not found.")

    messages = []
    for m in session.get("messages", []):
        g_raw = m.get("grounding")
        grounding = Grounding(**g_raw) if g_raw else None
        s_raw = m.get("sources")
        sources = [Source(**s) for s in s_raw] if s_raw else None
        u_raw = m.get("usage")
        usage = ChatMessageUsage(**u_raw) if u_raw else None
        messages.append(
            ChatMessageResponse(
                id=m["id"],
                role=m["role"],
                content=m["content"],
                grounding=grounding,
                sources=sources,
                usage=usage,
                created_at=m["created_at"],
            )
        )

    return ChatSessionResponse(
        id=session["id"],
        title=session["title"],
        scope=Scope(**session.get("scope", {"type": "all", "doc_ids": []})),
        updated_at=session["updated_at"],
        messages=messages,
    )


@router.patch("/chat/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_session(
    session_id: str,
    body: ChatSessionUpdate,
    c: AppContainer = Depends(get_container),
) -> ChatSessionResponse:
    """Update chat session title or document scope."""
    scope_data = body.scope.model_dump() if body.scope else None
    session = c.doc_store.update_chat_session(session_id, title=body.title, scope=scope_data)
    if not session:
        raise ApiError(status_code=404, code="not_found", detail=f"Chat session '{session_id}' not found.")
    return await get_session(session_id, c)


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, c: AppContainer = Depends(get_container)) -> dict[str, bool]:
    """Delete a chat session and its messages."""
    deleted = c.doc_store.delete_chat_session(session_id)
    if not deleted:
        raise ApiError(status_code=404, code="not_found", detail=f"Chat session '{session_id}' not found.")
    return {"deleted": True}


@router.get("/chat/sessions/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = Query(default="md"),
    c: AppContainer = Depends(get_container),
):
    """Export conversation history as markdown."""
    session = c.doc_store.get_chat_session(session_id)
    if not session:
        raise ApiError(status_code=404, code="not_found", detail=f"Chat session '{session_id}' not found.")

    lines = [f"# {session['title']}\n"]
    for m in session.get("messages", []):
        prefix = "**User**:" if m["role"] == "user" else "**Assistant**:"
        lines.append(f"{prefix}\n{m['content']}\n")
    return PlainTextResponse("\n".join(lines), media_type="text/markdown")


@router.post("/chat/sessions/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    body: SendMessage,
    request: Request,
    c: AppContainer = Depends(get_container),
):
    """Stream an answer to a chat message over SSE with grounding metadata."""
    if not c.chat_lock.acquire(blocking=False):
        raise ApiError(409, "generation_in_progress", "Another answer is still being generated")

    session = c.doc_store.get_chat_session(session_id)
    if not session:
        c.chat_lock.release()
        raise ApiError(404, "not_found", f"Chat session '{session_id}' not found.")

    history = c.doc_store.recent_chat_turns(session_id, limit=MAX_CHAT_TURNS)
    active_scope = body.scope.doc_ids[0] if (body.scope.type == "documents" and body.scope.doc_ids) else None
    doc_meta_map = _get_document_metadata_map(c)

    caps = c.ai_model.get_capabilities()
    context_window = getattr(caps, "context_window", 16384)

    def worker(emit: Emit, stop: threading.Event):
        with _STOPS_LOCK:
            _ACTIVE_STOPS[session_id] = stop
        try:
            emit("status", {"phase": "retrieving"})
            prepared = c.chat.prepare(
                prompt=body.content,
                history_before_turn=history,
                selected_doc=active_scope,
                document_metadata=doc_meta_map,
                retriever=c.retriever,
                context_window=context_window,
            )

            sources_payload = _format_sources(prepared.snippets)
            emit(
                "meta",
                {
                    "request_id": prepared.request_id,
                    "mode": prepared.mode,
                    "scope": {"type": body.scope.type, "doc_ids": body.scope.doc_ids},
                    "sources": sources_payload,
                },
            )

            if getattr(prepared, "incomplete_context", False) and not prepared.snippets:
                abstention = c.chat.abstention_turn(prepared)
                _finish(emit, c, session_id, body, abstention)
                return

            emit("status", {"phase": "generating"})
            chunks: list[str] = []
            t0 = time.perf_counter()
            ttft: float | None = None

            for tok in c.ai_model.ask_a_question_from_pdf_stream(
                prepared.search_query,
                retrieval_result=prepared.retrieval_result,
                chat_history=prepared.history,
                cancel=stop,
            ):
                if stop.is_set():
                    break
                if ttft is None:
                    ttft = (time.perf_counter() - t0) * 1000
                chunks.append(tok)
                emit("token", {"t": tok})

            emit("status", {"phase": "verifying"})
            raw_text = "".join(chunks)

            def do_regenerate(re_prompt: str) -> str:
                emit("status", {"phase": "regenerating"})
                reg_chunks: list[str] = []
                for t in c.ai_model.ask_a_question_from_pdf_stream(
                    re_prompt,
                    retrieval_result=prepared.retrieval_result,
                    chat_history=[],
                    cancel=stop,
                ):
                    if stop.is_set():
                        break
                    reg_chunks.append(t)
                return "".join(reg_chunks)

            assistant_turn = c.chat.finalize(
                prepared,
                raw_text,
                regenerate=do_regenerate,
                is_cloud=c.cloud.enabled,
            )

            if assistant_turn.get("content") != raw_text:
                emit("replace", {"answer_markdown": assistant_turn.get("content", "")})

            duration_ms = (time.perf_counter() - t0) * 1000
            _finish(
                emit,
                c,
                session_id,
                body,
                assistant_turn,
                ttft_ms=ttft or 0.0,
                duration_ms=duration_ms,
            )
        finally:
            with _STOPS_LOCK:
                _ACTIVE_STOPS.pop(session_id, None)
            c.chat_lock.release()

    return StreamingResponse(
        sse_from_worker(worker, request, on_error=problem_from_exc),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/chat/sessions/{session_id}/stop")
async def stop_generation(session_id: str) -> dict[str, bool]:
    """Cancel an active generation for a session."""
    with _STOPS_LOCK:
        stop_ev = _ACTIVE_STOPS.get(session_id)
        if stop_ev:
            stop_ev.set()
            return {"stopped": True}
    return {"stopped": False}
