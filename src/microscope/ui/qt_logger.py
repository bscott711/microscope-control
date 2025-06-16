# src/microscope/ui/qt_logger.py
import logging

from PySide6.QtCore import QObject, Signal


class _SignalEmitter(QObject):
    """A QObject that can emit a signal. For internal use by QtLogger."""

    new_log_entry = Signal(str)


class QtLogger(logging.Handler):
    """
    Custom logging handler that redirects logs to a Qt widget in a thread-safe manner.

    It uses a separate QObject with a signal to avoid inheriting from both
    logging.Handler and QObject, which would cause a method name collision for "emit".
    """

    def __init__(self, parent=None):
        super().__init__()
        self.emitter = _SignalEmitter(parent)
        # Expose the signal for easy connection
        self.new_log_entry = self.emitter.new_log_entry

    def emit(self, record: logging.LogRecord) -> None:
        """Formats and emits the log record via the signal emitter."""
        msg = self.format(record)
        self.emitter.new_log_entry.emit(msg)

    def write(self, text: str) -> None:
        """
        Stream interface for redirecting stdout/stderr.
        Only emits a signal if the text is not just whitespace.
        """
        if text.strip():
            self.emitter.new_log_entry.emit(text.strip())

    def flush(self) -> None:
        """Stream interface, required but does nothing for this handler."""
        pass
