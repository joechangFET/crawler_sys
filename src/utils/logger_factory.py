"""Build console and file loggers with level icons and per-URL progress.

Console icons fall back to ASCII when the stream cannot encode Unicode.
Existing handlers are reused to avoid duplicate output.
"""
import logging
import sys
import os
from datetime import datetime


class UrlProgressFilter(logging.Filter):
    """Prefix log messages with the active URL index without filtering records out."""
    def __init__(self):
        """Initialize the filter with no active URL progress."""
        super().__init__()
        self.current: int | None = None
        self.total: int | None = None

    def set_progress(self, current: int, total: int) -> None:
        """Set the URL index and total used for subsequent log records."""
        self.current = current
        self.total = total

    def clear_progress(self) -> None:
        """Disable URL prefixes by clearing the active counters."""
        self.current = None
        self.total = None

    def filter(self, record: logging.LogRecord) -> bool:
        """Add a URL prefix once and allow the record to reach its handlers."""
        if not self.current or not self.total:
            return True

        message = record.getMessage()
        if message.startswith("[URL "):
            return True

        record.msg = f"[URL {self.current}/{self.total}] {message}"
        record.args = ()
        return True


class IconFormatter(logging.Formatter):
    """Attach a level-specific icon to each record before standard formatting."""
    ICONS = {
        'DEBUG': '🐛',
        'INFO': '✅',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🔥',
    }

    def format(self, record: logging.LogRecord) -> str:
        """Populate levelicon and format the record with the configured log format."""
        icon = self.ICONS.get(record.levelname, '')
        record.levelicon = icon
        return super().format(record)

class LoggerFactory:
    """Create reusable loggers and manage their URL-progress filters."""
    URL_PROGRESS_FILTER_ATTR = "_url_progress_filter"

    @staticmethod
    def _supports_text(stream, text: str) -> bool:
        """Return whether the output stream encoding can represent the supplied text."""
        encoding = getattr(stream, "encoding", None) or "utf-8"
        try:
            text.encode(encoding)
            return True
        except (LookupError, UnicodeEncodeError):
            return False

    @staticmethod
    def _build_formatter(*, use_unicode_icons: bool) -> logging.Formatter:
        """Create a formatter using Unicode icons or ASCII level markers."""
        formatter = IconFormatter(
            "%(asctime)s | %(levelicon)s %(levelname)-8s | %(name)s | "
            "%(funcName)s:%(lineno)d | %(message)s"
        )
        if not use_unicode_icons:
            formatter.ICONS = {
                'DEBUG': '[D]',
                'INFO': '[I]',
                'WARNING': '[!]',
                'ERROR': '[E]',
                'CRITICAL': '[C]',
            }
        return formatter

    @staticmethod
    def create(
        *,
        name: str,
        log_dir: str | None = None,
        level: str = "INFO",
    ) -> logging.Logger:

        """Return a named logger with console output and an optional daily log file.

        Updates the log level but reuses existing handlers when already configured.
        """
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        logger.propagate = False

        if logger.handlers:
            return logger

        console_formatter = LoggerFactory._build_formatter(
            use_unicode_icons=LoggerFactory._supports_text(sys.stdout, "✅")
        )
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(console_formatter)
        logger.addHandler(console)

        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d")
            log_file = f"{name}_{ts}.log"
            file_path = os.path.join(
                log_dir,
                log_file
            )
            file_handler = logging.FileHandler(file_path, encoding="utf-8")
            file_handler.setFormatter(LoggerFactory._build_formatter(use_unicode_icons=True))
            logger.addHandler(file_handler)

        return logger

    @staticmethod
    def _get_url_progress_filter(logger: logging.Logger) -> UrlProgressFilter:
        """Return the logger's progress filter, creating and attaching it if absent."""
        progress_filter = getattr(logger, LoggerFactory.URL_PROGRESS_FILTER_ATTR, None)
        if progress_filter:
            return progress_filter

        progress_filter = UrlProgressFilter()
        logger.addFilter(progress_filter)
        setattr(logger, LoggerFactory.URL_PROGRESS_FILTER_ATTR, progress_filter)
        return progress_filter

    @staticmethod
    def set_url_progress(logger: logging.Logger, current: int, total: int) -> None:
        """Set the active URL progress on the supplied logger."""
        LoggerFactory._get_url_progress_filter(logger).set_progress(current, total)

    @staticmethod
    def clear_url_progress(logger: logging.Logger) -> None:
        """Clear the active URL progress on the supplied logger."""
        LoggerFactory._get_url_progress_filter(logger).clear_progress()
