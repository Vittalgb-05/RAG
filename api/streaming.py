"""Thread-to-SSE streaming bridge for thread-affine generation."""

from __future__ import annotations
import asyncio
import json
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any
from fastapi import Request

Emit = Callable[[str, dict[str, Any]], None]
_DONE = object()

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def sse(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def sse_from_worker(
    worker: Callable[[Emit, threading.Event], None],
    request: Request,
    on_error: Callable[[Exception], dict[str, Any]],
) -> AsyncIterator[str]:
    """Run `worker` on ONE dedicated thread (InferenceGate is thread-affine) and stream its events."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue[tuple[str, dict[str, Any]] | object] = asyncio.Queue()
    stop = threading.Event()

    def emit(event: str, data: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(q.put_nowait, (event, data))

    def run() -> None:
        try:
            worker(emit, stop)
        except Exception as exc:  # noqa: BLE001 - convert to a terminal SSE error event
            emit("error", on_error(exc))
        finally:
            loop.call_soon_threadsafe(q.put_nowait, _DONE)

    threading.Thread(target=run, name="rag-stream", daemon=True).start()
    try:
        while True:
            try:
                item = await asyncio.wait_for(q.get(), timeout=10)
            except asyncio.TimeoutError:
                if await request.is_disconnected():
                    stop.set()
                    break
                yield ": keepalive\n\n"
                continue
            if item is _DONE:
                break
            event, data = item  # type: ignore[misc]
            yield sse(event, data)
    finally:
        stop.set()  # client gone or finished -> worker checks this between tokens
