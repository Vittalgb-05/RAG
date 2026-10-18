"""Unit tests for logging_setup: suppression of the benign torch.classes watcher warning."""

import logging

from logging_setup import (
    WATCHER_LOGGER_NAME,
    TorchClassesScanLogFilter,
    suppress_torch_classes_scan_warning,
)


def test_filter_drops_torch_classes_scan_message():
    """The filter must reject the specific torch.classes file-watcher traceback."""
    logging_filter = TorchClassesScanLogFilter()
    record = logging.LogRecord(
        "x",
        logging.WARNING,
        __file__,
        1,
        "Examining the path of torch.classes raised:",
        None,
        None,
    )
    assert logging_filter.filter(record) is False


def test_filter_allows_unrelated_messages():
    """The filter must not hide any other log record from the watcher logger."""
    logging_filter = TorchClassesScanLogFilter()
    record = logging.LogRecord(
        "x",
        logging.WARNING,
        __file__,
        1,
        "Received event for non-watched file: app.py",
        None,
        None,
    )
    assert logging_filter.filter(record) is True


def test_suppress_is_idempotent():
    """Calling the installer twice must not stack duplicate filters."""
    logger = suppress_torch_classes_scan_warning("test.logging_setup.idempotent")
    suppress_torch_classes_scan_warning("test.logging_setup.idempotent")
    installed = [f for f in logger.filters if isinstance(f, TorchClassesScanLogFilter)]
    assert len(installed) == 1


def test_get_module_paths_torch_classes_warning_is_suppressed():
    """End-to-end: after suppression, scanning torch.classes emits no watcher warning."""
    import torch
    from streamlit.watcher.local_sources_watcher import get_module_paths

    watcher_logger = suppress_torch_classes_scan_warning(WATCHER_LOGGER_NAME)

    records: list[str] = []
    handler = logging.Handler()
    handler.emit = lambda record: records.append(record.getMessage())  # type: ignore[method-assign]
    watcher_logger.addHandler(handler)
    try:
        get_module_paths(torch.classes)
        assert not any("torch.classes" in message for message in records)

        # A genuine watcher warning must still be emitted after suppression.
        watcher_logger.warning("legitimate watcher warning")
        assert any("legitimate watcher warning" in message for message in records)
    finally:
        watcher_logger.removeHandler(handler)
