"""Unit tests for the thread-to-SSE streaming bridge."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from api.streaming import sse, sse_from_worker


def test_sse_formatting():
    frame = sse("token", {"token": "hello", "index": 0})
    assert frame.startswith("event: token\n")
    assert '"token": "hello"' in frame
    assert frame.endswith("\n\n")


@pytest.mark.asyncio
async def test_sse_from_worker_success():
    def worker(emit, stop):
        emit("token", {"token": "A", "index": 0})
        emit("token", {"token": "B", "index": 1})
        emit("done", {"metrics": {"tokens": 2}})

    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)

    events = []
    async for frame in sse_from_worker(worker, req, on_error=lambda e: {"msg": str(e)}):
        events.append(frame)

    assert len(events) == 3
    assert "event: token" in events[0]
    assert '"token": "A"' in events[0]
    assert "event: token" in events[1]
    assert '"token": "B"' in events[1]
    assert "event: done" in events[2]


@pytest.mark.asyncio
async def test_sse_from_worker_error():
    def worker(emit, stop):
        raise ValueError("Simulated inference failure")

    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)

    events = []
    async for frame in sse_from_worker(worker, req, on_error=lambda e: {"msg": str(e)}):
        events.append(frame)

    assert len(events) == 1
    assert "event: error" in events[0]
    assert "Simulated inference failure" in events[0]


@pytest.mark.asyncio
async def test_sse_from_worker_stops_on_disconnect():
    stop_signaled = False

    def worker(emit, stop):
        nonlocal stop_signaled
        emit("start", {})
        stop_signaled = stop.wait(timeout=2.0)

    req = MagicMock()
    req.is_disconnected = AsyncMock(return_value=False)

    stream = sse_from_worker(worker, req, on_error=lambda e: {"msg": str(e)})

    # Receive the initial event
    first_event = await stream.__anext__()
    assert "start" in first_event

    # Closing stream signals cancellation to background worker
    await stream.aclose()

    for _ in range(30):
        if stop_signaled:
            break
        await asyncio.sleep(0.05)
    assert stop_signaled is True
