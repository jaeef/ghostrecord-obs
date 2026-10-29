"""Live page: Obsidian Studio recording dashboard.

Shows the real-time state of the recording happening NOW: mono timer, pinned
target card (title / PID / HWND), status pills, decibel meter, silence banner,
OBS preview frame, activity feed, and the stop action.
"""

import time
from datetime import datetime

from PyQt6.QtCore import (QEasingCurve, QPropertyAnimation, Qt, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import QBrush, QColor, QPixmap
from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget,
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
    library_requested = pyqtSignal()
    capture_source_requested = pyqtSignal(str)
    record_chrome_requested = pyqtSignal()
    isolated_chrome_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._base_elapsed = 0.0
        self._base_time = 0.0
        self._last_path = ""
        self._pixmap = None
        self._silence_limit = 30.0
        self._silence_anim = None
        self._pid = 0
        self._hwnd = 0
        self._capture_safe = False

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # -- Timer -----------------------------------------------------------
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("bigTimer")
        lay.addWidget(self.timer_label)

        # -- Pinned target card ----------------------------------------------
        self.target_card = QWidget()
        self.target_card.setObjectName("targetCard")
        card_lay = QVBoxLayout(self.target_card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(4)
        self.target_title = ElidedLabel("—")
        title_font = self.target_title.font()
        title_font.setPointSize(title_font.pointSize() + 1)
        title_font.setBold(True)
        self.target_title.setFont(title_font)
        card_lay.addWidget(self.target_title)
        self.target_meta = QLabel("PID —  •  HWND —")
        self.target_meta.setObjectName("mono")
        card_lay.addWidget(self.target_meta)
        lock_note = QLabel("Locked by HWND — title changes are auto-tracked.")
        lock_note.setObjectName("muted")
        card_lay.addWidget(lock_note)
        lay.addWidget(self.target_card)

        # -- Status pills ------------------------------------------------------
        pills = QHBoxLayout()
        pills.setSpacing(8)
        self.pill_output = StatusPill("output idle", "idle")
        self.pill_min = StatusPill("window OK", "idle")
        self.pill_cover = StatusPill("", "idle")
        pills.addWidget(self.pill_output)
        pills.addWidget(self.pill_min)
        pills.addWidget(self.pill_cover)
        pills.addStretch(1)
        # quick fix: switch capture type without digging into Settings
        self.capture_combo = QComboBox()
        self.capture_combo.addItem("Capture: Window", "window")
        self.capture_combo.addItem("Capture: Game (sharp when covered)", "game")
        self.capture_combo.setToolTip(
            "Game Capture renders the app offscreen, so the recording stays "
            "sharp even when other windows cover it. Applies to the next "
            "recording.")
        pills.addWidget(self.capture_combo)
        lay.addLayout(pills)
        self.capture_combo.currentIndexChanged.connect(self._emit_capture_source)

        # -- Meter + silence banner --------------------------------------------
        self.meter = LevelMeter()
        lay.addWidget(self.meter)

        self.silence_banner = QLabel()
        self.silence_banner.setObjectName("silenceBanner")
        self.silence_banner.setVisible(False)
        self.silence_banner.setMaximumHeight(0)
        lay.addWidget(self.silence_banner)

        # -- advice banner (app stops rendering when covered) ------------------
        self.advice_box = QWidget()
        advice_lay = QHBoxLayout(self.advice_box)
        advice_lay.setContentsMargins(12, 8, 12, 8)
        advice_lay.setSpacing(10)
        self.advice_box.setObjectName("adviceBox")
        self.advice_label = QLabel("")
        self.advice_label.setWordWrap(True)
        self.advice_label.setObjectName("adviceText")
        self.advice_btn = QPushButton("🌐 Relaunch my Chrome")
        self.advice_btn.setObjectName("accent")
        self.advice_btn.setToolTip(
            "Restart your own Chrome with anti-throttle flags.\n"
            "Same profile, tabs restored, keeps drawing when covered.")
        self.advice_btn.clicked.connect(self.record_chrome_requested.emit)
        self.advice_iso_btn = QPushButton("🧪 Isolated Chrome")
        self.advice_iso_btn.setObjectName("accent")
        self.advice_iso_btn.setToolTip(
            "Open a separate Chrome instance (own profile) that never freezes.")
        self.advice_iso_btn.clicked.connect(self.isolated_chrome_requested.emit)
        self.advice_dismiss = QPushButton("✕")
        self.advice_dismiss.setObjectName("accent")
        self.advice_dismiss.setFixedWidth(32)
        self.advice_dismiss.clicked.connect(self.advice_box.hide)
        advice_lay.addWidget(self.advice_label, 1)
        advice_lay.addWidget(self.advice_btn)
        advice_lay.addWidget(self.advice_iso_btn)
        advice_lay.addWidget(self.advice_dismiss)
        self.advice_box.hide()
        lay.addWidget(self.advice_box)

        # -- Preview -------------------------------------------------------------
        self.preview = QLabel("Live preview appears while recording")
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(140)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.preview)

        # -- Error / result banners ---------------------------------------------
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
        self.open_file_btn = QPushButton("▶ Play")
        self.open_folder_btn = QPushButton("📂 Show in Explorer")
        self.back_btn = QPushButton("← Back to picker")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_folder_btn.clicked.connect(self._show_folder)
        self.back_btn.clicked.connect(self.back_requested.emit)
        for b in (self.open_file_btn, self.open_folder_btn):
            b.hide()
            result_btns.addWidget(b)
        result_btns.addStretch(1)
        lay.addLayout(result_btns)

        # -- Activity feed --------------------------------------------------------
        feed_title = QLabel("ACTIVITY")
        feed_title.setObjectName("dimmed")
        lay.addWidget(feed_title)
        self.feed = QListWidget()
        self.feed.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        lay.addWidget(self.feed, 1)

        # -- Actions ----------------------------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.stop_btn = QPushButton("■ Stop Recording & Save")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setMinimumHeight(38)
        self.stop_btn.setEnabled(False)
        controls.addWidget(self.stop_btn)
        self.library_btn = QPushButton("📁 View library")
        self.library_btn.clicked.connect(self.library_requested.emit)
        controls.addWidget(self.library_btn)
        controls.addStretch(1)
        lay.addLayout(controls)
        self.stop_btn.clicked.connect(self._on_stop_clicked)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick_label)
        self._ui_timer.start()

    # -- API used by the main window ----------------------------------------- #

    def set_silence_limit(self, seconds):
        self._silence_limit = float(seconds or 30)

    def set_capture_source(self, source):
        """Sync the quick capture-type combo (no signal emitted)."""
        idx = self.capture_combo.findData(source or "window")
        if idx < 0:
            idx = 0
        self.capture_combo.blockSignals(True)
        self.capture_combo.setCurrentIndex(idx)
        self.capture_combo.blockSignals(False)

    def _emit_capture_source(self, *_):
        self.capture_source_requested.emit(
            self.capture_combo.currentData() or "window")

    def on_capture_advice(self, ev):
        """Recorder detected an app that freezes itself when covered."""
        self._capture_safe = bool(ev.get("friendly"))
        if self._capture_safe:
            self.advice_box.hide()
            self.add_feed("obs", "target app keeps rendering when covered "
                                "— recording stays sharp")
            return
        exe = (ev.get("exe") or "this app").lower()
        if exe == "chrome.exe":
            self.advice_label.setText(
                "Chrome stops drawing when another window covers it, so the "
                "recording freezes. Pick how to fix it (one click):")
        else:
            self.advice_label.setText(
                f"{exe.replace('.exe', '')} stops drawing when another window "
                f"covers it, so the recording freezes. Pick a fix:")
        self.advice_box.show()

    # -- events from the recorder session ------------------------------------ #

    def begin_session(self):
        """Called when a new recording session is launched (before events)."""
        self._running = False
        self._last_path = ""
        self._pixmap = None
        self._pid = 0
        self._hwnd = 0
        self.preview.setPixmap(QPixmap())
        self.preview.setText("Waiting for the first frame…")
        self.feed.clear()
        self.banner.hide()
        self.result_label.hide()
        for b in (self.open_file_btn, self.open_folder_btn):
            b.hide()
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop Recording & Save")
        self.timer_label.setText("00:00:00")
        self.meter.set_enabled(False)
        self.meter.set_db(-100.0)
        self.pill_output.set_state("idle", "output idle")
        self.pill_min.set_state("idle", "window OK")
        self.pill_cover.hide()
        self.target_title.setText("—")
        self.target_meta.setText("PID —  •  HWND —")
        self.advice_box.hide()
        self._capture_safe = False
        self._hide_silence()

    def on_started(self, ev):
        self._running = True
        self._base_elapsed = 0.0
        self._base_time = time.time()
        self.stop_btn.setEnabled(True)
        self.stop_btn.setText("■ Stop Recording & Save")
        self._set_target(ev.get("window_title", ""), ev.get("pid", 0),
                         ev.get("hwnd", 0))
        self.pill_output.set_state("rec", "output active")
        self.pill_min.set_state("ok", "window OK")
        self.add_feed("rec", f"Recording started — '{ev.get('name', '')}'")

    def on_tick(self, ev):
        self._base_elapsed = float(ev.get("elapsed", 0.0))
        self._base_time = time.time()
        if ev.get("output_active", True):
            self.pill_output.set_state("rec", "output active")
        else:
            self.pill_output.set_state("warn", "output restarting…")
        if ev.get("minimized"):
            self.pill_min.set_state("warn", "minimized warning")
        else:
            self.pill_min.set_state("ok", "window OK")
        if ev.get("covered"):
            self.pill_cover.set_state("warn", "window covered — may blur")
            self.pill_cover.show()
        else:
            self.pill_cover.hide()
        if ev.get("pinned_title"):
            self._set_target(ev["pinned_title"],
                             ev.get("pid", self._pid),
                             ev.get("hwnd", self._hwnd))
        audio_on = bool(ev.get("audio_check"))
        self.meter.set_enabled(audio_on)
        db = float(ev.get("audio_db", -100.0))
        self.meter.set_db(db)
        silent_for = float(ev.get("silent_for", 0.0))
        if audio_on and silent_for > self._silence_limit:
            self._show_silence(
                f"🔇 No sound for {int(silent_for)}s "
                f"(last {db:.1f} dB) — check mic / speaker output.")
        else:
            self._hide_silence()

    def on_stopping(self, _ev):
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Finalizing…")
        self.pill_output.set_state("warn", "finalizing…")
        self._hide_silence()

    def on_stopped(self, ev):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop Recording & Save")
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
        self.pill_output.set_state("idle", "output idle")

    def on_aborted(self, reason):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.banner.setText(f"Recording aborted: {reason}")
        self.banner.show()

    def on_error(self, text):
        self._running = False
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ Stop Recording & Save")
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

    def _set_target(self, title, pid, hwnd):
        self._pid, self._hwnd = pid, hwnd
        self.target_title.setText(title or "—")
        pid_txt = pid if pid else "—"
        hwnd_txt = f"0x{hwnd:08X}" if hwnd else "—"
        self.target_meta.setText(f"PID {pid_txt}  •  HWND {hwnd_txt}")

    def _show_silence(self, text):
        self.silence_banner.setText(text)
        if not self.silence_banner.isVisible():
            self.silence_banner.setVisible(True)
        h = self.silence_banner.sizeHint().height()
        anim = QPropertyAnimation(self.silence_banner, b"maximumHeight", self)
        anim.setDuration(220)
        anim.setStartValue(self.silence_banner.maximumHeight())
        anim.setEndValue(h)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._silence_anim = anim

    def _hide_silence(self):
        if not self.silence_banner.isVisible():
            return
        anim = QPropertyAnimation(self.silence_banner, b"maximumHeight", self)
        anim.setDuration(180)
        anim.setStartValue(self.silence_banner.maximumHeight())
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(lambda: self.silence_banner.setVisible(False))
        anim.start()
        self._silence_anim = anim

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