"""Unit tests for logging_setup: suppression and application logging configuration."""

import logging

import pytest

from core.doc_store import DocStore
from core.logging_setup import (
    LOG_FILE_NAME,
    WATCHER_LOGGER_NAME,
    TorchClassesScanLogFilter,
    configure_logging,
    reset_logging,
    suppress_torch_classes_scan_warning,
)


@pytest.fixture(autouse=True)
def _clean_application_logging():
    """Remove module-owned handlers after each test so tmp dirs are not reused."""
    yield
    reset_logging()


def _managed_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger().handlers if getattr(h, "_rag_logging_handler", False)]


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


def test_configure_logging_is_idempotent(tmp_path):
    """Calling configure_logging twice must not stack duplicate handlers."""
    root = configure_logging(level="DEBUG", log_dir=tmp_path, force=True)
    assert len(_managed_handlers()) == 2  # stderr + rotating file

    configure_logging(level="DEBUG", log_dir=tmp_path)
    assert len(_managed_handlers()) == 2, "Duplicate handlers were installed"
    assert root.level == logging.DEBUG


def test_configure_logging_respects_environment_level(tmp_path, monkeypatch):
    """RAG_LOG_LEVEL must control the configured root level."""
    monkeypatch.setenv("RAG_LOG_LEVEL", "WARNING")
    root = configure_logging(log_dir=tmp_path, force=True)
    assert root.level == logging.WARNING


def test_configure_logging_writes_rotating_file(tmp_path):
    """The file handler must persist application log records under the log dir."""
    configure_logging(level="INFO", log_dir=tmp_path, force=True)
    logging.getLogger("tests.logging_setup").info("durable log line")

    for handler in logging.getLogger().handlers:
        handler.flush()

    log_text = (tmp_path / LOG_FILE_NAME).read_text(encoding="utf-8")
    assert "durable log line" in log_text


def test_configure_logging_degrades_when_log_dir_is_unwritable(tmp_path):
    """A path that cannot be used as a directory must not prevent configuration."""
    blocked_path = tmp_path / "not_a_directory"
    blocked_path.write_text("x", encoding="utf-8")

    configure_logging(log_dir=blocked_path, force=True)

    handlers = _managed_handlers()
    assert len(handlers) == 1, "Only the stderr handler should remain when file logging fails"
    assert isinstance(handlers[0], logging.StreamHandler)


def test_doc_store_migration_is_logged_not_printed(tmp_path, capsys):
    """The DocStore migration message must go through logging, not stdout."""
    DocStore(tmp_path / "migration_logging.db")
    captured = capsys.readouterr()
    assert "[DocStore]" not in captured.out
    assert "print(" not in captured.out


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
