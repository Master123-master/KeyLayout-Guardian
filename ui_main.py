"""
Main window, custom toggle switch, status indicator and system-tray plumbing.

Pure view + glue layer: it never calls Win32 directly (that lives in
win_layout) and never runs the enforcement loop itself (that lives in the
worker thread). This keeps the UI thread responsive at all times.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QPropertyAnimation, QRectF, Property, Signal, QThread
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap, QAction, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QPlainTextEdit, QFrame, QSystemTrayIcon, QMenu, QMessageBox, QApplication,
)

from . import win_layout
from .enforcement import EnforcementWorker
from .settings import AppSettings
from .style import STYLESHEET, COLORS


# ---------------------------------------------------------------------------
# Custom animated toggle switch
# ---------------------------------------------------------------------------
class ToggleSwitch(QWidget):
    """A modern animated on/off switch driven by an internal QPropertyAnimation."""

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self._offset = 3.0
        self.setFixedSize(56, 30)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)

    # Qt animatable property -------------------------------------------------
    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    # Public API -------------------------------------------------------------
    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, emit: bool = True) -> None:
        if checked == self._checked:
            return
        self._checked = checked
        self._animate()
        if emit:
            self.toggled.emit(self._checked)

    def _animate(self) -> None:
        start = self._offset
        end = (self.width() - self.height() + 3) if self._checked else 3.0
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    # Interaction & painting -------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QColor(COLORS["green"]) if self._checked else QColor(COLORS["border"])
        p.setBrush(track)
        p.setPen(Qt.NoPen)
        radius = self.height() / 2
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), radius, radius)
        # Knob
        p.setBrush(QColor("#ffffff"))
        knob = self.height() - 6
        p.drawEllipse(QRectF(self._offset, 3, knob, knob))


# ---------------------------------------------------------------------------
# Status indicator (coloured dot + label)
# ---------------------------------------------------------------------------
class StatusIndicator(QWidget):
    """Green 'Protected' / red 'Not Protected' badge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._protected = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._dot = QLabel()
        self._dot.setFixedSize(12, 12)
        self._text = QLabel()
        self._text.setObjectName("FieldValue")
        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addStretch()
        self.set_protected(False)

    def set_protected(self, protected: bool) -> None:
        self._protected = protected
        color = COLORS["green"] if protected else COLORS["red"]
        self._dot.setStyleSheet(f"background:{color}; border-radius:6px;")
        self._text.setText("Protected" if protected else "Not Protected")
        self._text.setStyleSheet(f"color:{color}; font-weight:600;")


def _make_app_icon() -> QIcon:
    """Generate a simple, crisp icon at runtime (no external asset needed)."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(COLORS["accent"]))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(6, 6, 52, 52, 14, 14)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI", 26, QFont.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignCenter, "K")
    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KeyLayout Guardian")
        self.setMinimumWidth(420)
        self.setMaximumWidth(520)
        self.setStyleSheet(STYLESHEET)

        self._settings = AppSettings.load()
        self._layouts: list[win_layout.KeyboardLayout] = []
        self._allow_close = False

        self.setWindowIcon(_make_app_icon())

        self._build_ui()
        self._populate_layouts()
        self._start_worker()
        self._build_tray()
        self._restore_settings()

    # -- UI construction ----------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # Header
        header = QVBoxLayout()
        title = QLabel("KeyLayout Guardian")
        title.setObjectName("Title")
        subtitle = QLabel("Locks your keyboard layout against unwanted switches")
        subtitle.setObjectName("Subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        # --- Protection card ---
        prot_card = self._card()
        prot_layout = QVBoxLayout(prot_card)
        prot_layout.setContentsMargins(16, 16, 16, 16)
        prot_layout.setSpacing(12)

        toggle_row = QHBoxLayout()
        self.indicator = StatusIndicator()
        self.toggle = ToggleSwitch()
        self.toggle.toggled.connect(self._on_toggle)
        toggle_row.addWidget(self.indicator, 1)
        toggle_row.addWidget(self.toggle, 0, Qt.AlignRight)
        prot_layout.addLayout(toggle_row)

        # Layout selector
        prot_layout.addWidget(self._field_label("Enforced keyboard layout"))
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self._on_layout_changed)
        prot_layout.addWidget(self.combo)

        root.addWidget(prot_card)

        # --- Status card ---
        status_card = self._card()
        s_layout = QVBoxLayout(status_card)
        s_layout.setContentsMargins(16, 16, 16, 16)
        s_layout.setSpacing(10)

        self.selected_value = self._status_row(s_layout, "Selected layout")
        self.status_value = self._status_row(s_layout, "Protection status")
        self.active_value = self._status_row(s_layout, "Active Windows layout")
        root.addWidget(status_card)

        # --- Log section ---
        log_header = QHBoxLayout()
        self.log_toggle_btn = QPushButton("▸  Activity log")
        self.log_toggle_btn.setStyleSheet("text-align:left;")
        self.log_toggle_btn.clicked.connect(self._toggle_log)
        log_header.addWidget(self.log_toggle_btn)
        root.addLayout(log_header)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(150)
        self.log_view.setVisible(False)
        root.addWidget(self.log_view)

        root.addStretch()

    def _card(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("Card")
        return frame

    def _field_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FieldLabel")
        return lbl

    def _status_row(self, parent_layout: QVBoxLayout, label: str) -> QLabel:
        row = QHBoxLayout()
        name = QLabel(label)
        name.setObjectName("FieldLabel")
        value = QLabel("—")
        value.setObjectName("FieldValue")
        value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(name)
        row.addWidget(value, 1)
        parent_layout.addLayout(row)
        return value

    # -- Layout list --------------------------------------------------------
    def _populate_layouts(self) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self._layouts = win_layout.list_installed_layouts()
        for layout in self._layouts:
            self.combo.addItem(layout.display_name, layout.langid)
        self.combo.blockSignals(False)

    def _current_layout(self) -> win_layout.KeyboardLayout | None:
        idx = self.combo.currentIndex()
        if 0 <= idx < len(self._layouts):
            return self._layouts[idx]
        return None

    # -- Worker thread ------------------------------------------------------
    def _start_worker(self) -> None:
        self._thread = QThread(self)
        self._worker = EnforcementWorker()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)

        self._worker.layout_observed.connect(self._on_layout_observed)
        self._worker.correction_made.connect(self._on_correction)
        self._worker.log_message.connect(self._log)

        self._thread.start()

    # -- Settings -----------------------------------------------------------
    def _restore_settings(self) -> None:
        # Restore the previously selected layout, if still installed.
        if self._settings.selected_langid is not None:
            for i, layout in enumerate(self._layouts):
                if layout.langid == self._settings.selected_langid:
                    self.combo.setCurrentIndex(i)
                    break

        layout = self._current_layout()
        if layout:
            self._worker.set_target_layout(layout)
            self.selected_value.setText(layout.display_name)

        # Restore log panel state.
        if self._settings.log_panel_expanded:
            self._toggle_log()

        # Restore protection state last so everything is wired up.
        if self._settings.protection_enabled:
            self.toggle.setChecked(True)  # triggers _on_toggle

    def _persist(self) -> None:
        layout = self._current_layout()
        self._settings.selected_langid = layout.langid if layout else None
        self._settings.protection_enabled = self.toggle.isChecked()
        self._settings.log_panel_expanded = self.log_view.isVisible()
        self._settings.save()

    # -- Event handlers -----------------------------------------------------
    def _on_layout_changed(self, _index: int) -> None:
        layout = self._current_layout()
        if layout:
            self._worker.set_target_layout(layout)
            self.selected_value.setText(layout.display_name)
            self._log(f"Selected layout: {layout.display_name}")
        self._persist()

    def _on_toggle(self, enabled: bool) -> None:
        self._worker.set_enabled(enabled)
        self.indicator.set_protected(enabled)
        self.status_value.setText("Enabled" if enabled else "Disabled")
        self.status_value.setStyleSheet(
            f"color:{COLORS['green'] if enabled else COLORS['red']};font-weight:600;"
        )
        self._sync_tray_action()
        self._persist()

    def _on_layout_observed(self, _hkl: int, name: str) -> None:
        self.active_value.setText(name)

    def _on_correction(self, from_name: str, to_name: str) -> None:
        self._log(f"Layout changed to '{from_name}' — restored to '{to_name}'")

    def _toggle_log(self) -> None:
        visible = not self.log_view.isVisible()
        self.log_view.setVisible(visible)
        self.log_toggle_btn.setText(
            ("▾  Activity log" if visible else "▸  Activity log")
        )
        self.adjustSize()
        self._persist()

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}]  {message}")

    # -- System tray --------------------------------------------------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("KeyLayout Guardian")

        menu = QMenu()
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self._show_window)
        self.tray_toggle_action = QAction("Enable Protection", self)
        self.tray_toggle_action.triggered.connect(self._tray_toggle)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._exit_app)

        menu.addAction(show_action)
        menu.addAction(self.tray_toggle_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._sync_tray_action()

    def _sync_tray_action(self) -> None:
        self.tray_toggle_action.setText(
            "Disable Protection" if self.toggle.isChecked() else "Enable Protection"
        )

    def _tray_toggle(self) -> None:
        self.toggle.setChecked(not self.toggle.isChecked())

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:  # single left click
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # -- Window lifecycle ---------------------------------------------------
    def closeEvent(self, event) -> None:
        """Closing the window minimises to tray instead of quitting."""
        if self._allow_close:
            self._shutdown()
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "KeyLayout Guardian",
            "Still running in the background. Right-click the tray icon to exit.",
            QSystemTrayIcon.Information,
            2500,
        )

    def _exit_app(self) -> None:
        self._allow_close = True
        self.close()
        QApplication.quit()

    def _shutdown(self) -> None:
        """Cleanly stop the worker thread before exit."""
        self._persist()
        self._worker.stop()
        self._thread.quit()
        self._thread.wait(2000)
        self.tray.hide()
