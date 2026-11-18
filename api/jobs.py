"""Background job manager with single-worker execution for GPU contention control."""

from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import datetime
import logging
import threading
import time
from typing import Any
from collections.abc import AsyncIterator, Callable
import uuid

logger = logging.getLogger(__name__)


@dataclass
class JobEvent:
    """An event emitted during job execution."""

    event: str
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass
class Job:
    """Background task descriptor."""

    job_id: str
    kind: str
    status: str = "queued"  # queued, running, completed, failed, cancelled
    stage: str = "queued"
    pct: float | None = 0.0
    message: str = ""
    error: str | None = None
    result: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)
    events: list[JobEvent] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat())

    def update(self, stage: str, pct: float | None, message: str = "") -> None:
        """Update job progress and emit an event."""
        self.stage = stage
        self.pct = pct
        self.message = message
        self.updated_at = datetime.datetime.now(datetime.UTC).isoformat()
        self.events.append(
            JobEvent(
                "progress",
                {
                    "job_id": self.job_id,
                    "stage": stage,
                    "pct": pct,
                    "message": message,
                },
            )
        )


class JobHandle:
    """Handle passed to background workers to check cancellation and report progress."""

    def __init__(self, job: Job) -> None:
        self._job = job

    @property
    def cancelled(self) -> threading.Event:
        return self._job.cancel

    def progress(self, stage: str, pct: float | None, message: str = "") -> None:
        self._job.update(stage=stage, pct=pct, message=message)


class JobManager:
    """ONE worker: ingestion, OCR, VLM, summarization all contend for the same GPU/memory."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rag-job")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, fn: Callable[[JobHandle], Any], **meta: Any) -> Job:
        """Submit a task to the background worker pool."""
        job_id = str(uuid.uuid4())
        job = Job(job_id=job_id, kind=kind, meta=meta)
        with self._lock:
            self._jobs[job_id] = job

        handle = JobHandle(job)

        def runner() -> None:
            if job.cancel.is_set():
                job.status = "cancelled"
                job.events.append(JobEvent("cancelled", {"job_id": job_id}))
                return

            job.status = "running"
            job.events.append(JobEvent("started", {"job_id": job_id, "kind": kind}))
            try:
                res = fn(handle)
                if job.cancel.is_set():
                    job.status = "cancelled"
                    job.events.append(JobEvent("cancelled", {"job_id": job_id}))
                else:
                    job.status = "completed"
                    job.result = res
                    job.pct = 100.0
                    job.events.append(
                        JobEvent(
                            "done",
                            {
                                "job_id": job_id,
                                "result": res if isinstance(res, (dict, list, str, int, float, bool)) else None,
                            },
                        )
                    )
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                job.events.append(JobEvent("error", {"job_id": job_id, "error": str(exc)}))
                logger.error("Job %s (%s) failed: %s", job_id, kind, exc, exc_info=True)
            finally:
                job.updated_at = datetime.datetime.now(datetime.UTC).isoformat()

        self._pool.submit(runner)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self._lock:
            return list(reversed(list(self._jobs.values())))[:limit]

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            job.cancel.set()
            if job.status == "queued":
                job.status = "cancelled"
                job.events.append(JobEvent("cancelled", {"job_id": job_id}))
            return True

    async def events(self, job_id: str) -> AsyncIterator[str]:
        """Stream SSE events for a job by polling events, 250ms interval."""
        from api.streaming import sse

        idx = 0
        while True:
            job = self.get(job_id)
            if not job:
                yield sse("error", {"job_id": job_id, "error": "Job not found"})
                break

            while idx < len(job.events):
                ev = job.events[idx]
                idx += 1
                yield sse(ev.event, ev.data)

            if job.status in ("completed", "failed", "cancelled"):
                while idx < len(job.events):
                    ev = job.events[idx]
                    idx += 1
                    yield sse(ev.event, ev.data)
                break

            await asyncio.sleep(0.25)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
