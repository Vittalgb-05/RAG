"""System health, diagnostics, telemetry, and log endpoints."""

from __future__ import annotations
import asyncio
import datetime
import logging
import os
import psutil
from typing import Literal
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from api.container import AppContainer
from api.deps import get_container
from api.schemas.system import (
    Diagnostics,
    GpuTelemetry,
    Health,
    HealthCapabilities,
    HealthRuntime,
    IndexIntegrityItem,
    InferenceTelemetry,
    LogEntry,
    ProcessTelemetry,
    Telemetry,
)
from api.streaming import SSE_HEADERS, sse
from core.redaction import redact_text

router = APIRouter(tags=["system"])


def _build_health(c: AppContainer) -> Health:
    ready = c.ready.is_set()
    mode: Literal["local", "cloud"] = "cloud" if c.cloud.enabled else "local"
    provider = c.cloud.provider if c.cloud.enabled else "local"
    model = c.cloud.model if c.cloud.enabled else (getattr(c.ai_model, "model_path", None) or "local")

    try:
        p_status = c.ai_model.check_health()
        is_healthy = getattr(p_status, "status", "") == "healthy"
        msg = getattr(p_status, "message", "OK")
    except Exception as exc:
        is_healthy = False
        msg = str(exc)

    status_str: Literal["healthy", "loading", "unreachable", "offline"]
    if not ready:
        status_str = "loading"
        msg = "Background hydration in progress"
    elif is_healthy:
        status_str = "healthy"
    else:
        status_str = "unreachable"

    caps = c.ai_model.get_capabilities()
    capabilities = HealthCapabilities(
        context_window=getattr(caps, "context_window", 16384),
        supports_vision=getattr(caps, "supports_vision", False),
        supports_streaming=getattr(caps, "supports_streaming", True),
    )

    runtime = HealthRuntime(
        llama_server_version=getattr(c.ai_model, "server_version", None),
        build=getattr(c.ai_model, "build_id", None),
    )

    return Health(
        status=status_str,
        message=msg,
        ready=ready,
        mode=mode,
        provider=provider,
        model=model,
        capabilities=capabilities,
        runtime=runtime,
    )


def _collect_telemetry(c: AppContainer) -> Telemetry:
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    rss_mb = round(mem.rss / (1024 * 1024), 2)
    vms_mb = round(mem.vms / (1024 * 1024), 2)

    gpu_telemetry: GpuTelemetry | None = None
    try:
        import torch

        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
            allocated = torch.cuda.memory_allocated(0) / (1024 * 1024)
            free = total - allocated
            gpu_telemetry = GpuTelemetry(
                total_mb=round(total, 2),
                used_mb=round(allocated, 2),
                free_mb=round(free, 2),
            )
    except Exception:
        pass

    return Telemetry(
        gpu=gpu_telemetry,
        process=ProcessTelemetry(rss_mb=rss_mb, vms_mb=vms_mb),
        inference=InferenceTelemetry(busy=c.chat_lock.locked()),
        ts=datetime.datetime.now(datetime.UTC).isoformat(),
    )


@router.get("/health", response_model=Health)
async def get_health(c: AppContainer = Depends(get_container)) -> Health:
    """Retrieve system health status, mode, and model capabilities."""
    return _build_health(c)


@router.get("/telemetry", response_model=Telemetry)
async def get_telemetry(c: AppContainer = Depends(get_container)) -> Telemetry:
    """Get instant system telemetry (GPU, RAM, and inference lock)."""
    return _collect_telemetry(c)


@router.get("/telemetry/stream")
async def stream_telemetry(request: Request, c: AppContainer = Depends(get_container)):
    """Stream live telemetry events over SSE."""

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            telemetry = _collect_telemetry(c)
            yield sse("telemetry", telemetry.model_dump())
            await asyncio.sleep(2.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.get("/diagnostics", response_model=Diagnostics)
async def get_diagnostics(c: AppContainer = Depends(get_container)) -> Diagnostics:
    """Inspect index integrity, tombstones, and startup hydration details."""
    health = _build_health(c)
    tombstones = c.doc_store.list_deletion_tombstones()
    docs = c.doc_store.list_documents()

    degraded = []
    for doc in docs:
        if doc.status == "indexed":
            has_vec = c.retriever.has_document(doc.doc_id)
            if not has_vec:
                degraded.append(
                    IndexIntegrityItem(
                        doc_id=doc.doc_id,
                        filename=doc.filename,
                        status=doc.status,
                        missing_vectors=True,
                        num_chunks=doc.num_chunks,
                    )
                )

    hyd_dict = None
    if c.hydration:
        hyd_dict = {
            "restored": c.hydration.restored,
            "repaired": c.hydration.repaired,
            "failed": c.hydration.failed,
            "tombstones_consumed": c.hydration.tombstones_consumed,
        }

    return Diagnostics(
        health=health,
        tombstones=tombstones,
        degraded_documents=degraded,
        hydration=hyd_dict,
    )


_LEVEL_WEIGHTS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


@router.get("/diagnostics/logs", response_model=list[LogEntry])
async def get_logs(
    lines: int = Query(default=100, ge=1, le=1000),
    level: str = Query(default="INFO"),
    c: AppContainer = Depends(get_container),
) -> list[LogEntry]:
    """Retrieve redacted recent application logs."""
    log_file = c.settings.log_dir / "app.log"
    if not log_file.exists():
        log_file = c.settings.log_dir / "rag.log"
    if not log_file.exists():
        return []

    min_weight = _LEVEL_WEIGHTS.get(level.strip().upper(), logging.INFO)
    entries: list[LogEntry] = []
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        for raw_line in all_lines:
            line_str = raw_line.strip()
            if not line_str:
                continue
            clean_line = redact_text(line_str)
            parts = clean_line.split(" ", 2)
            ts = parts[0] if parts else ""
            lvl = parts[1].upper() if len(parts) > 1 else "INFO"
            msg = parts[2] if len(parts) > 2 else clean_line
            entry_weight = _LEVEL_WEIGHTS.get(lvl, logging.INFO)
            if entry_weight >= min_weight:
                entries.append(LogEntry(timestamp=ts, level=lvl, message=msg))
    except Exception:
        pass
    return entries[-lines:]
