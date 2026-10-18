"""Logging configuration helpers for the Streamlit entry point.

Provides :class:`TorchClassesScanLogFilter`, a targeted filter that silences a
benign Streamlit startup traceback. Streamlit's file watcher probes every
imported module for a ``__path__`` attribute, and the ``torch.classes`` module
raises ``RuntimeError`` (instead of ``AttributeError``) when probed, so the
watcher logs a harmless traceback on every launch. Filtering only that specific
message keeps the file watcher and all other Streamlit logging intact.
"""

import logging

WATCHER_LOGGER_NAME = "streamlit.watcher.local_sources_watcher"


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
