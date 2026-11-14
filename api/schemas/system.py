"""System health, diagnostics, and telemetry schemas."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


HealthStatus = Literal["healthy", "loading", "unreachable", "offline"]


class HealthCapabilities(BaseModel):
    """Runtime LLM capabilities."""

    context_window: int = 16384
    supports_vision: bool = False
    supports_streaming: bool = True


class HealthRuntime(BaseModel):
    """Runtime binary/process build information."""

    llama_server_version: str | None = None
    build: str | None = None


class Health(BaseModel):
    """Health check response."""

    status: HealthStatus
    message: str
    ready: bool
    mode: Literal["local", "cloud"]
    provider: str
    model: str
    capabilities: HealthCapabilities
    runtime: HealthRuntime


class GpuTelemetry(BaseModel):
    """GPU memory metrics in megabytes."""

    total_mb: float
    used_mb: float
    free_mb: float


class ProcessTelemetry(BaseModel):
    """Process memory footprint."""

    rss_mb: float
    vms_mb: float


class InferenceTelemetry(BaseModel):
    """Inference lock status."""

    busy: bool


class Telemetry(BaseModel):
    """System resource telemetry."""

    gpu: GpuTelemetry | None = None
    process: ProcessTelemetry
    inference: InferenceTelemetry
    ts: str


class IndexIntegrityItem(BaseModel):
    """Document integrity item."""

    doc_id: str
    filename: str
    status: str
    missing_vectors: bool
    num_chunks: int


class Diagnostics(BaseModel):
    """Detailed system diagnostic status."""

    health: Health
    tombstones: list[str] = Field(default_factory=list)
    degraded_documents: list[IndexIntegrityItem] = Field(default_factory=list)
    hydration: dict[str, int] | None = None


class LogEntry(BaseModel):
    """Redacted log entry."""

    timestamp: str
    level: str
    message: str
