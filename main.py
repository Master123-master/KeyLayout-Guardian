"""
Application entry point.

Ensures a single instance via a named QSharedMemory lock, configures the
Qt application, and shows the main window.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QSharedMemory
from PySide6.QtWidgets import QApplication, QMessageBox

from .ui_main import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("KeyLayout Guardian")
    app.setOrganizationName("KeyLayout Guardian")
    # Keep running when the last window is hidden (we live in the tray).
    app.setQuitOnLastWindowClosed(False)

    # --- Single-instance guard ---
    shared = QSharedMemory("KeyLayoutGuardian_SingleInstance")
    if not shared.create(1):
        QMessageBox.information(
            None,
            "KeyLayout Guardian",
            "KeyLayout Guardian is already running.\n"
            "Check the system tray (near the clock).",
        )
        return 0

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
