"""Logging configuration helpers for the Streamlit entry point.

Provides two concerns:

* :func:`configure_logging` installs a single, idempotent application logging
  configuration (stderr plus an optional rotating file under ``data/logs/``).
  The level is controlled by the ``RAG_LOG_LEVEL`` environment variable or an
  explicit argument.  CLI launchers (``start.py`` / ``setup.py``) intentionally
  keep their ``print()``-based operator output.
* :class:`TorchClassesScanLogFilter` silences a benign Streamlit startup
  traceback.  Streamlit's file watcher probes every imported module for a
  ``__path__`` attribute, and the ``torch.classes`` module raises
  ``RuntimeError`` (instead of ``AttributeError``) when probed, so the watcher
  logs a harmless traceback on every launch.  Filtering only that specific
  message keeps the file watcher and all other Streamlit logging intact.
"""

from collections.abc import Iterable
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

WATCHER_LOGGER_NAME = "streamlit.watcher.local_sources_watcher"

LOG_LEVEL_ENV = "RAG_LOG_LEVEL"
LOG_DIR_ENV = "RAG_LOG_DIR"
DEFAULT_LOG_DIR = Path("data") / "logs"
LOG_FILE_NAME = "app.log"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

# Marker attribute used to identify handlers installed by this module.  It lets
# repeated calls reconfigure our own handlers without touching handlers that
# Streamlit, pytest, or the host application installed.
_HANDLER_MARKER = "_rag_logging_handler"

_MAX_LOG_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3


def _resolve_level(level: str | int | None) -> int:
    """Resolve a log level from an explicit value or the environment."""
    if level is None:
        level = os.environ.get(LOG_LEVEL_ENV, "INFO")
    if isinstance(level, str):
        resolved = logging.getLevelName(level.strip().upper())
        # getLevelName returns a string for unknown names on Python < 3.11.
        return resolved if isinstance(resolved, int) else logging.INFO
    return int(level)


def _managed_handlers(handlers: Iterable[logging.Handler]) -> list[logging.Handler]:
    """Return the handlers previously installed by :func:`configure_logging`."""
    return [handler for handler in handlers if getattr(handler, _HANDLER_MARKER, False)]


def configure_logging(
    level: str | int | None = None,
    log_dir: str | Path | None = None,
    *,
    enable_file: bool = True,
    force: bool = False,
) -> logging.Logger:
    """Install the application logging configuration on the root logger.

    The function is idempotent: calling it twice leaves exactly one stderr
    handler (and one rotating file handler when enabled).  Existing handlers
    owned by other frameworks are left untouched.

    Args:
        level: Explicit level (name or numeric).  Defaults to ``RAG_LOG_LEVEL``
            or ``INFO`` when the variable is unset/invalid.
        log_dir: Directory for the rotating log file.  Defaults to
            ``RAG_LOG_DIR`` or ``data/logs``.  The directory is created if
            needed.
        enable_file: Set to False to configure stderr only (used by tests and
            environments without a writable data directory).
        force: Remove and recreate handlers installed by a previous call.  Use
            this after changing configuration in a long-lived process.

    Returns:
        The configured root logger.
    """
    root = logging.getLogger()
    existing = _managed_handlers(root.handlers)

    if existing and not force:
        # Still honour an explicit level request so callers can raise/lower
        # verbosity without duplicating handlers.
        resolved = _resolve_level(level)
        root.setLevel(resolved)
        for handler in existing:
            handler.setLevel(resolved)
        return root

    for handler in existing:
        root.removeHandler(handler)
        try:
            handler.close()
        except (OSError, RuntimeError) as close_err:  # pragma: no cover - defensive close
            logging.getLogger(__name__).debug("Could not close old log handler: %s", close_err)

    resolved_level = _resolve_level(level)
    root.setLevel(resolved_level)

    formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(resolved_level)
    setattr(stream_handler, _HANDLER_MARKER, True)
    root.addHandler(stream_handler)

    if enable_file:
        target_dir = Path(log_dir) if log_dir is not None else Path(os.environ.get(LOG_DIR_ENV, DEFAULT_LOG_DIR))
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                target_dir / LOG_FILE_NAME,
                maxBytes=_MAX_LOG_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(resolved_level)
            setattr(file_handler, _HANDLER_MARKER, True)
            root.addHandler(file_handler)
        except OSError as err:
            # A read-only or missing data directory must not prevent startup.
            logging.getLogger(__name__).warning("File logging disabled for %s: %s", target_dir, err)

    return root


def reset_logging() -> None:
    """Remove handlers installed by :func:`configure_logging` (test helper)."""
    root = logging.getLogger()
    for handler in _managed_handlers(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except (OSError, RuntimeError) as close_err:  # pragma: no cover - defensive close
            logging.getLogger(__name__).debug("Could not close log handler during reset: %s", close_err)


class TorchClassesScanLogFilter(logging.Filter):
    """Drop Streamlit's benign file-watcher traceback for the ``torch.classes`` module.

    A filter is used rather than ``Logger.setLevel`` because Streamlit's
    ``get_logger`` calls ``setLevel`` when a module is first imported, which would
    clobber a level change made before that import. Filters are not reset this way.
    """

    _needle = "torch.classes"

    def filter(self, record: logging.LogRecord) -> bool:
        """Return False only for the known torch.classes scan warning."""
        return self._needle not in record.getMessage()


def suppress_torch_classes_scan_warning(
    logger_name: str = WATCHER_LOGGER_NAME,
) -> logging.Logger:
    """Attach :class:`TorchClassesScanLogFilter` to the Streamlit watcher logger.

    Idempotent: repeated calls will not stack duplicate filters.

    Args:
        logger_name: Name of the logger to filter (defaults to Streamlit's watcher logger).

    Returns:
        The filtered logger instance.
    """
    watcher_logger = logging.getLogger(logger_name)
    if not any(isinstance(f, TorchClassesScanLogFilter) for f in watcher_logger.filters):
        watcher_logger.addFilter(TorchClassesScanLogFilter())
    return watcher_logger
