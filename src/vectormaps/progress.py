"""A spinner for the slow steps, drawn only when stderr is a terminal.

Log lines and the spinner share the same line of the terminal, so the log
handler erases the spinner before it prints and the spinner redraws after.
"""

import logging
import sys
import threading
import time

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
CLEAR = "\r\033[K"

_lock = threading.RLock()
_active: "Spinner | None" = None


class Spinner:
    def __init__(self, message: str, stream=None, interval: float = 0.1):
        self.message = message
        self.stream = stream or sys.stderr
        self.interval = interval
        self.enabled = bool(getattr(self.stream, "isatty", lambda: False)())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start = 0.0

    def __enter__(self) -> "Spinner":
        global _active
        self._start = time.monotonic()
        if self.enabled:
            with _lock:
                _active = self
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> bool:
        global _active
        if self._thread is not None:
            self._stop.set()
            self._thread.join()
            with _lock:
                _active = None
                self.clear()
        return False

    def clear(self) -> None:
        self.stream.write(CLEAR)
        self.stream.flush()

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            elapsed = int(time.monotonic() - self._start)
            with _lock:
                if _active is self:
                    frame = FRAMES[i % len(FRAMES)]
                    self.stream.write(f"{CLEAR}{frame} {self.message} ({elapsed}s)")
                    self.stream.flush()
            i += 1
            self._stop.wait(self.interval)


class ProgressHandler(logging.StreamHandler):
    """A log handler that does not trample the spinner."""

    def emit(self, record: logging.LogRecord) -> None:
        with _lock:
            if _active is not None:
                _active.clear()
            super().emit(record)
