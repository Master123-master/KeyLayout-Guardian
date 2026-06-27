"""
Background enforcement worker.

Runs on its own QThread so the UI stays perfectly responsive. It polls the
foreground window's keyboard layout and, when protection is enabled, corrects
any deviation from the user-selected layout.

Communication with the GUI is done exclusively through Qt signals, which are
thread-safe.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal, QMutex, QMutexLocker

from . import win_layout
from .win_layout import KeyboardLayout

# Poll interval in milliseconds. 120 ms is imperceptible to the user yet keeps
# CPU usage negligible (a few microseconds of work per tick).
POLL_INTERVAL_MS = 120


class EnforcementWorker(QObject):
    """Owns the enforcement loop. Lives inside a dedicated QThread."""

    # Emitted whenever the live foreground layout is observed (hkl, name).
    layout_observed = Signal(int, str)
    # Emitted when an unwanted change is detected and corrected (from, to).
    correction_made = Signal(str, str)
    # Emitted for human-readable log lines.
    log_message = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._mutex = QMutex()
        self._target: KeyboardLayout | None = None
        self._enabled: bool = False
        self._running: bool = False
        self._last_observed_hkl: int = 0

    # -- Thread-safe configuration setters ---------------------------------

    def set_target_layout(self, layout: KeyboardLayout) -> None:
        with QMutexLocker(self._mutex):
            self._target = layout

    def set_enabled(self, enabled: bool) -> None:
        with QMutexLocker(self._mutex):
            self._enabled = enabled
        if enabled:
            self.log_message.emit("Protection enabled.")
        else:
            self.log_message.emit("Protection disabled.")

    def stop(self) -> None:
        with QMutexLocker(self._mutex):
            self._running = False

    # -- Main loop ---------------------------------------------------------

    def run(self) -> None:
        """Entry point invoked when the thread starts."""
        self._running = True
        self.log_message.emit("Monitoring service started.")

        # We use a simple, robust loop with QThread.msleep rather than a
        # QTimer to keep the worker self-contained and predictable.
        while True:
            with QMutexLocker(self._mutex):
                if not self._running:
                    break
                enabled = self._enabled
                target = self._target

            try:
                self._tick(enabled, target)
            except Exception as exc:  # never let the loop die
                self.log_message.emit(f"Recoverable error: {exc}")

            QThread.msleep(POLL_INTERVAL_MS)

        self.log_message.emit("Monitoring service stopped.")

    def _tick(self, enabled: bool, target: KeyboardLayout | None) -> None:
        """One iteration of the enforcement loop."""
        current_hkl = win_layout.get_foreground_layout_hkl()

        # Report live status only when it actually changes (reduces signal spam).
        if current_hkl != self._last_observed_hkl:
            self._last_observed_hkl = current_hkl
            self.layout_observed.emit(
                current_hkl, win_layout.langname_for_hkl(current_hkl)
            )

        if not enabled or target is None:
            return

        # Compare by language id (low word) so different physical layouts of
        # the same language are treated as a match where appropriate.
        if (current_hkl & 0xFFFF) != (target.langid & 0xFFFF):
            from_name = win_layout.langname_for_hkl(current_hkl)
            win_layout.enforce_layout(target)
            self.correction_made.emit(from_name, target.display_name)
