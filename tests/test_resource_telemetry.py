"""Unit tests for resource telemetry and latency profiling module."""

from collections.abc import Generator
import subprocess
import time
from unittest.mock import MagicMock, patch

import pytest

from resource_telemetry import (
    clear_latency_history,
    get_gpu_memory_info,
    get_latency_history,
    get_process_memory_info,
    get_system_telemetry_snapshot,
    LatencyTracker,
    record_stage_latency,
    track_stage,
)


@pytest.fixture(autouse=True)
def reset_latencies() -> Generator[None, None, None]:
    """Ensure clean latency history state before and after each test."""
    clear_latency_history()
    yield
    clear_latency_history()


def test_get_gpu_memory_info_success() -> None:
    """Test parsing standard nvidia-smi output."""
    mock_res = MagicMock()
    mock_res.stdout = "4096, 1024, 3072\n"

    with patch("subprocess.run", return_value=mock_res):
        info = get_gpu_memory_info()

    assert info is not None
    assert info["total_mb"] == 4096.0
    assert info["used_mb"] == 1024.0
    assert info["free_mb"] == 3072.0
    assert info["utilization_pct"] == 25.0


def test_get_gpu_memory_info_empty_or_malformed() -> None:
    """Test graceful handling of empty or incomplete nvidia-smi output."""
    mock_res = MagicMock()
    mock_res.stdout = "   \n"

    with patch("subprocess.run", return_value=mock_res):
        assert get_gpu_memory_info() is None

    mock_res.stdout = "4096, 1024\n"
    with patch("subprocess.run", return_value=mock_res):
        assert get_gpu_memory_info() is None


def test_get_gpu_memory_info_subprocess_failures() -> None:
    """Test graceful degradation to None when nvidia-smi fails or is absent."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        assert get_gpu_memory_info() is None

    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["nvidia-smi"]),
    ):
        assert get_gpu_memory_info() is None

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(["nvidia-smi"], 2.0),
    ):
        assert get_gpu_memory_info() is None


def test_get_process_memory_info_live() -> None:
    """Test live retrieval of current process memory info."""
    mem = get_process_memory_info()
    assert isinstance(mem, dict)
    assert "rss_mb" in mem
    assert "vms_mb" in mem
    assert mem["rss_mb"] >= 0.0
    assert mem["vms_mb"] >= 0.0


def test_get_process_memory_info_fallback_on_error() -> None:
    """Test fallback to zeros if psutil raises an exception."""
    with patch("psutil.Process", side_effect=RuntimeError("psutil access error")):
        mem = get_process_memory_info()
        assert mem == {"rss_mb": 0.0, "vms_mb": 0.0}


def test_latency_tracker_success() -> None:
    """Test LatencyTracker measures elapsed duration and marks success."""
    with LatencyTracker("test_stage") as tracker:
        time.sleep(0.02)

    assert tracker.stage_name == "test_stage"
    assert tracker.success is True
    assert tracker.error is None
    assert tracker.elapsed_ms >= 15.0

    data = tracker.to_dict()
    assert data["stage"] == "test_stage"
    assert data["success"] is True

    history = get_latency_history()
    assert "test_stage" in history
    assert len(history["test_stage"]) == 1
    assert history["test_stage"][0] == tracker.elapsed_ms


def test_latency_tracker_exception() -> None:
    """Test LatencyTracker captures failure details when block raises."""
    with pytest.raises(ValueError, match="Intentional failure"):
        with LatencyTracker("failing_stage") as tracker:
            time.sleep(0.01)
            raise ValueError("Intentional failure")

    assert tracker.success is False
    assert tracker.error == "Intentional failure"
    assert tracker.elapsed_ms > 0.0

    history = get_latency_history()
    assert "failing_stage" in history


def test_track_stage_context_manager() -> None:
    """Test track_stage convenience context manager."""
    with track_stage("convenience_stage") as tracker:
        time.sleep(0.01)

    assert tracker.success is True
    assert tracker.elapsed_ms > 0.0


def test_record_and_get_latency_history() -> None:
    """Test manual recording and retrieval of latency history."""
    record_stage_latency("manual_stage", 42.5)
    record_stage_latency("manual_stage", 57.5)

    history = get_latency_history()
    assert history["manual_stage"] == [42.5, 57.5]

    clear_latency_history()
    assert get_latency_history() == {}


def test_get_system_telemetry_snapshot() -> None:
    """Test system telemetry snapshot structure and stage metrics aggregation."""
    record_stage_latency("map_stage", 100.0)
    record_stage_latency("map_stage", 200.0)

    snap = get_system_telemetry_snapshot()
    assert "timestamp" in snap
    assert "gpu" in snap
    assert "process" in snap
    assert "stages" in snap

    stages = snap["stages"]
    assert "map_stage" in stages
    assert stages["map_stage"]["count"] == 2
    assert stages["map_stage"]["avg_ms"] == 150.0
    assert stages["map_stage"]["min_ms"] == 100.0
    assert stages["map_stage"]["max_ms"] == 200.0
