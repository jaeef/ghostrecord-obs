"""Live page: recording status — timer, pinned window, pills, meter, feed."""

import time
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPixmap
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPushButton, QVBoxLayout,
                             QWidget)

from ghostrec.core.library import open_file, show_in_explorer
from ghostrec.ui import theme
from ghostrec.ui.widgets import ElidedLabel, LevelMeter, StatusPill

_MAX_FEED = 200


def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class LivePage(QWidget):
    stop_requested = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._base_elapsed = 0.0
        self._base_time = 0.0
        self._last_path = ""
        self._pixmap = None

        lay = QVBoxLayout(self)

        title = QLabel("Live recording")
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("bigTimer")
        lay.addWidget(self.timer_label)

        self.window_label = ElidedLabel("—")
        font = self.window_label.font()
        font.setPointSize(font.pointSize() + 1)
        self.window_label.setFont(font)
        lay.addWidget(self.window_label)

        self.hwnd_label = QLabel("")
        self.hwnd_label.setObjectName("muted")
        lay.addWidget(self.hwnd_label)

        pills = QHBoxLayout()
        self.pill_output = StatusPill("output —", "idle")
        self.pill_min = StatusPill("window OK", "idle")
        pills.addWidget(self.pill_output)
        pills.addWidget(self.pill_min)
        pills.addStretch(1)
        lay.addLayout(pills)

        self.meter = LevelMeter()
        lay.addWidget(self.meter)

        self.preview = QLabel("Live preview appears while recording")
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(190)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.preview)

        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        lay.addWidget(self.banner)

        self.result_label = ElidedLabel("")
        self.result_label.setObjectName("okBanner")
        self.result_label.hide()
        lay.addWidget(self.result_label)

        result_btns = QHBoxLayout()
        self.open_file_btn = QPushButton("Open file")
        self.open_folder_btn = QPushButton("Show in folder")
        self.back_btn = QPushButton("Back to picker")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_folder_btn.clicked.connect(self._show_folder)
        self.back_btn.clicked.connect(self.back_requested.emit)
        for b in (self.open_file_btn, self.open_folder_btn, self.back_btn):
            b.hide()
            result_btns.addWidget(b)
        result_btns.addStretch(1)
        lay.addLayout(result_btns)

        feed_title = QLabel("Activity")
        feed_title.setObjectName("muted")
        lay.addWidget(feed_title)
        self.feed = QListWidget()
        self.feed.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        lay.addWidget(self.feed, 1)

        controls = QHBoxLayout()
        self.stop_btn = QPushButton("■ Stop & save")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.stop_btn)
        controls.addStretch(1)
        lay.addLayout(controls)
        self.stop_btn.clicked.connect(self._on_stop_clicked)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick_label)
        self._ui_timer.start()

    # -- events from the recorder session ------------------------------------ #

    def begin_session(self):
        """Called when a new recording session is launched (before events)."""
        self._running = False
        self._last_path = ""
        self._pixmap = None
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Waiting for the first frame…")
        self.feed.clear()
        self.banner.hide()
        self.result_label.hide()
        for b in (self.open_file_btn, self.open_folder_btn):
            b.hide()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop & save")
        self.timer_label.setText("00:00:00")
        self.meter.set_enabled(False)
        self.pill_output.set_state("idle", "output —")
        self.pill_min.set_state("idle", "window OK")

    def on_started(self, ev):
        self._running = True
        self._base_elapsed = 0.0
        self._base_time = time.time()
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("■ Stop & save")
        self.window_label.setText(ev.get("window_title", ""))
        self.hwnd_label.setText(f"locked to hwnd {ev.get('hwnd', '?')}")
        self.pill_output.set_state("rec", "recording")
        self.pill_min.set_state("ok", "window OK")
        self.add_feed("rec", f"Recording started — '{ev.get('name', '')}'")

    def on_tick(self, ev):
        self._base_elapsed = float(ev.get("elapsed", 0.0))
        self._base_time = time.time()
        if ev.get("output_active", True):
            self.pill_output.set_state("rec", "recording")
        else:
            self.pill_output.set_state("warn", "restarting output…")
        if ev.get("minimized"):
            self.pill_min.set_state("warn", "MINIMIZED — frozen!")
        else:
            self.pill_min.set_state("ok", "window OK")
        if ev.get("pinned_title"):
            self.window_label.setText(ev["pinned_title"])
        self.meter.set_enabled(bool(ev.get("audio_check")))
        self.meter.set_db(float(ev.get("audio_db", -100.0)))

    def on_stopping(self, _ev):
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Finalizing…")
        self.pill_output.set_state("warn", "finalizing…")

    def on_stopped(self, ev):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop & save")
        self._last_path = ev.get("final_path") or ""
        if ev.get("timed_out"):
            self.banner.setText("File finalization timed out — the recording "
                                "may be incomplete and was left in OBS's "
                                "recording folder.\n"
                                f"{ev.get('src_path', '')}")
            self.banner.show()
        if self._last_path:
            self.result_label.setText(f"Saved: {self._last_path}")
            self.result_label.show()
            self.open_file_btn.show()
            self.open_folder_btn.show()
        self.pill_output.set_state("idle", "output —")

    def on_aborted(self, reason):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.banner.setText(f"Recording aborted: {reason}")
        self.banner.show()

    def on_error(self, text):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop & save")
        self.banner.setText(f"Error: {text}")
        self.banner.show()

    def add_feed(self, source, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"{stamp}  [{source}] {text}")
        if source == "error":
            item.setForeground(QBrush(QColor(theme.ERR)))
        elif "⚠" in text or "WARNING" in text.upper():
            item.setForeground(QBrush(QColor(theme.WARN)))
        elif "✔" in text:
            item.setForeground(QBrush(QColor(theme.OK)))
        self.feed.addItem(item)
        while self.feed.count() > _MAX_FEED:
            self.feed.takeItem(0)
        self.feed.scrollToBottom()

    # -- live preview --------------------------------------------------------- #

    def set_preview(self, raw):
        """Show a JPEG frame (bytes) fetched from OBS."""
        pm = QPixmap()
        if raw and pm.loadFromData(raw):
            self._pixmap = pm
            self.preview.setText("")
            self._apply_preview()

    def set_preview_error(self, text):
        self._pixmap = None
        self.preview.setPixmap(QPixmap())
        self.preview.setText(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_preview()

    def _apply_preview(self):
        if self._pixmap is None:
            return
        self.preview.setPixmap(self._pixmap.scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))

    # -- internals ------------------------------------------------------------ #

    def _tick_label(self):
        if not self._running:
            return
        elapsed = self._base_elapsed + (time.time() - self._base_time)
        self.timer_label.setText(_hms(elapsed))

    def _on_stop_clicked(self):
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stopping…")
        self.stop_requested.emit()

    def _open_file(self):
        if self._last_path:
            open_file(self._last_path)

    def _show_folder(self):
        if self._last_path:
            show_in_explorer(self._last_path)
