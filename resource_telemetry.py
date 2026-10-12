"""Resource telemetry and performance profiling module.

Provides live monitoring of GPU VRAM (via nvidia-smi with graceful CI/headless degradation),
process memory (RSS and VMS via psutil), stage execution latency tracking, and snapshot
aggregations for benchmarking 4 GB VRAM systems (QUAL-01).
"""

from collections import defaultdict
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
import logging
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# Global latency history registry for benchmarking and diagnostic introspection
_LATENCY_HISTORY: dict[str, list[float]] = defaultdict(list)
_LATENCY_LOCK = threading.Lock()
MAX_STAGE_HISTORY: int = 200


def get_gpu_memory_info() -> dict[str, float] | None:
    """Query NVIDIA GPU memory via nvidia-smi.

    Returns:
        Dictionary with total_mb, used_mb, free_mb, utilization_pct,
        or None if nvidia-smi is unavailable, fails, or runs in a headless/CI environment.
    """
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=2.0,
        )
        stdout = result.stdout.strip()
        if not stdout:
            return None

        primary_line = stdout.splitlines()[0]
        parts = [x.strip() for x in primary_line.split(",")]
        if len(parts) < 3:
            return None

        total_mb = float(parts[0])
        used_mb = float(parts[1])
        free_mb = float(parts[2])
        utilization_pct = round((used_mb / total_mb) * 100.0, 1) if total_mb > 0 else 0.0

        return {
            "total_mb": round(total_mb, 1),
            "used_mb": round(used_mb, 1),
            "free_mb": round(free_mb, 1),
            "utilization_pct": utilization_pct,
        }
    except (FileNotFoundError, subprocess.SubprocessError, ValueError, IndexError) as err:
        logger.debug("GPU telemetry unavailable via nvidia-smi: %s", err)
        return None
    except Exception as err:
        logger.debug("Unexpected error querying nvidia-smi: %s", err)
        return None


def get_process_memory_info() -> dict[str, float]:
    """Query current process resident set size (RSS) and virtual memory (VMS).

    Uses psutil when available, falling back gracefully to zeros in constrained environments.

    Returns:
        Dictionary containing rss_mb and vms_mb.
    """
    try:
        import psutil

        proc = psutil.Process()
        mem = proc.memory_info()
        return {
            "rss_mb": round(mem.rss / (1024 * 1024), 2),
            "vms_mb": round(mem.vms / (1024 * 1024), 2),
        }
    except ImportError:
        logger.debug("psutil is not installed; reporting zero process memory")
        return {"rss_mb": 0.0, "vms_mb": 0.0}
    except Exception as err:
        logger.debug("Error querying process memory via psutil: %s", err)
        return {"rss_mb": 0.0, "vms_mb": 0.0}


class LatencyTracker:
    """Context manager and tracker for stage-by-stage execution latency."""

    def __init__(self, stage_name: str, record_history: bool = True) -> None:
        """Initialize tracker with a stage identifier.

        Args:
            stage_name: Name of pipeline stage (e.g. 'pdf_extraction', 'hybrid_retrieval').
            record_history: Whether to append elapsed duration to global latency history.
        """
        self.stage_name = stage_name
        self.record_history = record_history
        self._start_perf: float = 0.0
        self._end_perf: float | None = None
        self.elapsed_ms: float = 0.0
        self.success: bool = False
        self.error: str | None = None

    def __enter__(self) -> "LatencyTracker":
        """Start wall-clock timing."""
        self._start_perf = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop timing, compute duration in ms, and record metrics."""
        self._end_perf = time.perf_counter()
        self.elapsed_ms = round((self._end_perf - self._start_perf) * 1000.0, 2)
        if exc_type is None:
            self.success = True
            self.error = None
        else:
            self.success = False
            self.error = str(exc_val)

        if self.record_history:
            with _LATENCY_LOCK:
                history = _LATENCY_HISTORY[self.stage_name]
                history.append(self.elapsed_ms)
                if len(history) > MAX_STAGE_HISTORY:
                    _LATENCY_HISTORY[self.stage_name] = history[-MAX_STAGE_HISTORY:]

    def to_dict(self) -> dict[str, Any]:
        """Convert tracker outcome to dictionary."""
        return {
            "stage": self.stage_name,
            "elapsed_ms": self.elapsed_ms,
            "success": self.success,
            "error": self.error,
        }


@contextmanager
def track_stage(stage_name: str) -> Generator[LatencyTracker, None, None]:
    """Convenience generator context manager for tracking stage execution."""
    tracker = LatencyTracker(stage_name)
    with tracker:
        yield tracker


def record_stage_latency(stage_name: str, elapsed_ms: float) -> None:
    """Directly record an elapsed duration into latency history."""
    with _LATENCY_LOCK:
        history = _LATENCY_HISTORY[stage_name]
        history.append(round(elapsed_ms, 2))
        if len(history) > MAX_STAGE_HISTORY:
            _LATENCY_HISTORY[stage_name] = history[-MAX_STAGE_HISTORY:]


def get_latency_history() -> dict[str, list[float]]:
    """Return a thread-safe copy of the recorded latency history."""
    with _LATENCY_LOCK:
        return {stage: list(durations) for stage, durations in _LATENCY_HISTORY.items()}


def clear_latency_history() -> None:
    """Clear recorded latency history."""
    with _LATENCY_LOCK:
        _LATENCY_HISTORY.clear()


def get_system_telemetry_snapshot() -> dict[str, Any]:
    """Capture an instantaneous snapshot of system resources and latency metrics.

    Returns:
        Structured dictionary containing timestamp, gpu, process, and summary latencies.
    """
    gpu_info = get_gpu_memory_info()
    proc_info = get_process_memory_info()

    with _LATENCY_LOCK:
        history_copy = {stage: list(durations) for stage, durations in _LATENCY_HISTORY.items()}

    stage_summaries: dict[str, dict[str, float]] = {}
    for stage, times in history_copy.items():
        if times:
            stage_summaries[stage] = {
                "count": len(times),
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": min(times),
                "max_ms": max(times),
            }

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gpu": gpu_info,
        "process": proc_info,
        "stages": stage_summaries,
    }
