"""Live page: recording dashboard (preview + inspector).

Shows the real-time state of the recording happening NOW: mono timer, pinned
target card (title / PID / HWND), status pills, decibel meter, silence banner,
OBS preview frame, activity feed, and the stop action.
"""

import time
from datetime import datetime

from PyQt6.QtCore import (QEasingCurve, QPropertyAnimation, Qt, QTimer,
                          pyqtSignal)
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                              QListWidget, QListWidgetItem, QPushButton,
                              QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ghostrec.core.library import open_file, show_in_explorer
from ghostrec.ui import dialogs
from ghostrec.ui.widgets import (ActivityLog, ElidedLabel, LevelMeter,
                                 StatusPill)



def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class LivePage(QWidget):
    stop_requested = pyqtSignal()
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

        # Two columns. Left: notices, preview, activity. Right: a fixed-width
        # inspector whose content SCROLLS instead of being squeezed, with the
        # Stop button pinned at its bottom.
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(10)
        root.addLayout(left, 1)

        # -- notices (only visible when relevant) --------------------------------
        self.silence_banner = QLabel()
        self.silence_banner.setObjectName("silenceBanner")
        self.silence_banner.setWordWrap(True)
        self.silence_banner.setVisible(False)
        self.silence_banner.setMaximumHeight(0)
        left.addWidget(self.silence_banner)

        self.advice_box = QWidget()
        self.advice_box.setObjectName("adviceBox")
        self.advice_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,
                                     True)
        advice = QVBoxLayout(self.advice_box)
        advice.setContentsMargins(14, 10, 10, 10)
        advice.setSpacing(8)
        advice_top = QHBoxLayout()
        advice_top.setSpacing(10)
        advice_icon = QLabel("⚠")
        advice_icon.setObjectName("noticeIconWarn")
        self.advice_label = QLabel("")
        self.advice_label.setWordWrap(True)
        self.advice_label.setObjectName("adviceText")
        self.advice_dismiss = QPushButton("✕")
        self.advice_dismiss.setObjectName("closeButton")
        self.advice_dismiss.setFixedSize(22, 22)
        self.advice_dismiss.clicked.connect(self.advice_box.hide)
        advice_top.addWidget(advice_icon, 0, Qt.AlignmentFlag.AlignTop)
        advice_top.addWidget(self.advice_label, 1)
        advice_top.addWidget(self.advice_dismiss, 0, Qt.AlignmentFlag.AlignTop)
        advice.addLayout(advice_top)
        advice_btns = QHBoxLayout()
        advice_btns.addStretch(1)
        self.advice_iso_btn = QPushButton("Open Safe Browser")
        self.advice_iso_btn.setToolTip(
            "Open a separate Chrome with its own recording-safe profile.")
        self.advice_iso_btn.clicked.connect(self.isolated_chrome_requested.emit)
        self.advice_btn = QPushButton("Make Recording-Safe")
        self.advice_btn.setObjectName("accent")
        self.advice_btn.setToolTip(
            "Restart this app once with recording-safe settings so it keeps "
            "drawing while covered. Applies to the next recording.")
        self.advice_btn.clicked.connect(self.record_chrome_requested.emit)
        advice_btns.addWidget(self.advice_iso_btn)
        advice_btns.addWidget(self.advice_btn)
        advice.addLayout(advice_btns)
        self.advice_box.hide()
        left.addWidget(self.advice_box)

        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        left.addWidget(self.banner)

        self.result_box = QWidget()
        self.result_box.setObjectName("resultBox")
        self.result_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,
                                     True)
        result_row = QHBoxLayout(self.result_box)
        result_row.setContentsMargins(14, 8, 8, 8)
        result_row.setSpacing(8)
        ok_icon = QLabel("✓")
        ok_icon.setObjectName("noticeIconOk")
        self.result_label = ElidedLabel("")
        self.result_label.setObjectName("resultText")
        self.open_file_btn = QPushButton("Play")
        self.open_folder_btn = QPushButton("Show in Folder")
        self.open_file_btn.clicked.connect(self._open_file)
        self.open_folder_btn.clicked.connect(self._show_folder)
        result_row.addWidget(ok_icon)
        result_row.addWidget(self.result_label, 1)
        result_row.addWidget(self.open_folder_btn)
        result_row.addWidget(self.open_file_btn)
        self.result_box.hide()
        left.addWidget(self.result_box)

        # -- preview ----------------------------------------------------------------
        self.preview = QLabel("Live preview appears here while recording")
        self.preview.setObjectName("preview")
        self.preview.setMinimumSize(280, 160)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored,
                                   QSizePolicy.Policy.Ignored)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.preview, 1)

        # -- activity ----------------------------------------------------------------
        self.feed = ActivityLog()
        self.feed.setFixedHeight(176)
        left.addWidget(self.feed)

        # -- inspector ---------------------------------------------------------------
        inspector = QWidget()
        inspector.setObjectName("inspector")
        inspector.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        inspector.setFixedWidth(300)
        ins_outer = QVBoxLayout(inspector)
        ins_outer.setContentsMargins(0, 0, 0, 0)
        ins_outer.setSpacing(0)
        root.addWidget(inspector)

        scroll = QScrollArea()
        scroll.setObjectName("inspectorScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("inspectorBody")
        ins = QVBoxLayout(body)
        ins.setContentsMargins(18, 16, 18, 12)
        ins.setSpacing(6)
        scroll.setWidget(body)
        ins_outer.addWidget(scroll, 1)

        # timer
        state_row = QHBoxLayout()
        state_row.setSpacing(8)
        self.state_label = QLabel("Ready")
        self.state_label.setObjectName("sectionHeader")
        state_row.addWidget(self.state_label)
        state_row.addStretch(1)
        self.rec_badge = QLabel("● REC")
        self.rec_badge.setObjectName("recBadge")
        self.rec_badge.hide()
        state_row.addWidget(self.rec_badge)
        ins.addLayout(state_row)
        self.timer_label = QLabel("00:00:00")
        self.timer_label.setObjectName("bigTimer")
        ins.addWidget(self.timer_label)
        ins.addSpacing(8)

        # target
        ins.addWidget(self._section("Target"))
        self.target_card = QWidget()
        self.target_card.setObjectName("groupCard")
        self.target_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,
                                      True)
        card_lay = QVBoxLayout(self.target_card)
        card_lay.setContentsMargins(12, 10, 12, 10)
        card_lay.setSpacing(3)
        self.target_title = ElidedLabel("No window selected")
        self.target_title.setObjectName("cardTitle")
        card_lay.addWidget(self.target_title)
        self.target_meta = QLabel("PID —  •  HWND —")
        self.target_meta.setObjectName("mono")
        card_lay.addWidget(self.target_meta)
        ins.addWidget(self.target_card)
        ins.addSpacing(8)

        # status rows
        ins.addWidget(self._section("Status"))
        status_card = QWidget()
        status_card.setObjectName("groupCard")
        status_card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        status = QVBoxLayout(status_card)
        status.setContentsMargins(12, 4, 12, 4)
        status.setSpacing(0)
        self.pill_output = StatusPill("Idle", "idle")
        self.pill_min = StatusPill("—", "idle")
        self.pill_cover = StatusPill("—", "idle")
        for i, (label, pill) in enumerate((("Output", self.pill_output),
                                           ("Window", self.pill_min),
                                           ("Covered", self.pill_cover))):
            if i:
                status.addWidget(self._separator())
            status.addWidget(self._status_row(label, pill))
        ins.addWidget(status_card)
        ins.addSpacing(8)

        # audio
        ins.addWidget(self._section("Audio"))
        self.meter = LevelMeter()
        self.meter.setMinimumWidth(200)
        ins.addWidget(self.meter)
        ins.addSpacing(8)

        # capture type
        ins.addWidget(self._section("Capture"))
        self.capture_combo = QComboBox()
        self.capture_combo.addItem("Window · covered mode", "window")
        self.capture_combo.addItem("Game capture", "game")
        self.capture_combo.setToolTip(
            "Window + Modern WGC is the reliable default for a restored window "
            "covered by another app. Game Capture is only for apps that support "
            "OBS game hooks. Applies to the next recording.")
        ins.addWidget(self.capture_combo)
        self.capture_combo.currentIndexChanged.connect(self._emit_capture_source)
        hint = QLabel("Keep the window restored. Covering it is fine; "
                      "minimizing pauses the picture.")
        hint.setObjectName("dimmed")
        hint.setWordWrap(True)
        ins.addSpacing(4)
        ins.addWidget(hint)
        ins.addStretch(1)

        # pinned actions
        footer = QWidget()
        footer.setObjectName("inspectorFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(18, 12, 18, 16)
        foot.setSpacing(8)
        self.stop_btn = QPushButton("Stop && Save")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setMinimumHeight(32)
        self.stop_btn.setEnabled(False)
        foot.addWidget(self.stop_btn)
        self.library_btn = QPushButton("Show Library")
        self.library_btn.clicked.connect(self.library_requested.emit)
        foot.addWidget(self.library_btn)
        ins_outer.addWidget(footer)
        self.stop_btn.clicked.connect(self._on_stop_clicked)

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(1000)
        self._ui_timer.timeout.connect(self._tick_label)
        self._ui_timer.start()

    # -- building blocks ------------------------------------------------------ #

    @staticmethod
    def _section(text):
        lbl = QLabel(text.upper())
        lbl.setObjectName("sectionLabel")
        return lbl

    @staticmethod
    def _separator():
        line = QFrame()
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        return line

    @staticmethod
    def _status_row(label, pill):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 7, 0, 7)
        name = QLabel(label)
        name.setObjectName("rowLabel")
        lay.addWidget(name)
        lay.addStretch(1)
        lay.addWidget(pill)
        return row

    def _set_state(self, text):
        self.state_label.setText(text)

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
        name = ev.get("app") or (ev.get("exe") or "this app").replace(".exe", "")
        self.advice_label.setText(
            f"<b>{name} may freeze while covered.</b><br>It stops drawing when "
            "another window is on top. Make it recording-safe for your next "
            "recording.")
        self.advice_box.show()

    def on_relocked(self, ev):
        """Show a title change without treating it as a new target."""
        title = ev.get("title", "")
        if title:
            self.target_title.setText(title)
        self.add_feed("pin", f"re-locked same window — '{title}'")

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
        self.result_box.hide()
        self._set_state("Starting…")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stop && Save")
        self.capture_combo.setEnabled(False)
        self.timer_label.setText("00:00:00")
        self.meter.set_enabled(False)
        self.meter.set_db(-100.0)
        self.pill_output.set_state("idle", "Idle")
        self.pill_min.set_state("idle", "—")
        self.pill_cover.set_state("idle", "—")
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
        self.stop_btn.setText("Stop && Save")
        self.rec_badge.show()
        self._set_state("Recording")
        self._set_target(ev.get("window_title", ""), ev.get("pid", 0),
                         ev.get("hwnd", 0))
        self.pill_output.set_state("rec", "Recording")
        self.pill_min.set_state("ok", "Visible")
        self.pill_cover.set_state("idle", "No")
        self.add_feed("rec", f"Recording started — '{ev.get('name', '')}'")

    def on_tick(self, ev):
        self._base_elapsed = float(ev.get("elapsed", 0.0))
        self._base_time = time.time()
        if ev.get("output_active", True):
            self.pill_output.set_state("rec", "Recording")
        else:
            self.pill_output.set_state("warn", "Restarting…")
        if ev.get("minimized"):
            self.pill_min.set_state("warn", "Minimized")
        else:
            self.pill_min.set_state("ok", "Visible")
        if ev.get("covered") and ev.get("capture_method") == 2:
            self.pill_cover.set_state("ok", "Protected")
        elif ev.get("covered"):
            self.pill_cover.set_state("warn", "Legacy capture")
        else:
            self.pill_cover.set_state("idle", "No")
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
                f"No sound for {int(silent_for)}s "
                f"(last {db:.1f} dB) — check mic / speaker output.")
        else:
            self._hide_silence()

    def on_stopping(self, _ev):
        self.rec_badge.hide()
        self._set_state("Saving…")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Finalizing…")
        self.pill_output.set_state("warn", "Finalizing…")
        self._hide_silence()

    def on_stopped(self, ev):
        self._running = False
        self.capture_combo.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stop && Save")
        self._last_path = ev.get("final_path") or ""
        if ev.get("timed_out"):
            self.banner.setText("File finalization timed out — the recording "
                                "may be incomplete and was left in OBS's "
                                "recording folder.\n"
                                f"{ev.get('src_path', '')}")
            self.banner.show()
        if self._last_path:
            self.result_label.setText(f"Saved  {self._last_path}")
            self.result_box.show()
        self._set_state("Saved" if self._last_path else "Stopped")
        self.pill_output.set_state("idle", "Idle")

    def on_aborted(self, reason):
        self._running = False
        self.rec_badge.hide()
        self._set_state("Not started")
        self.capture_combo.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.banner.setText(f"Recording aborted: {reason}")
        self.banner.show()

    def on_error(self, text):
        self._running = False
        self.rec_badge.hide()
        self._set_state("Stopped")
        self.capture_combo.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("Stop && Save")
        self.banner.setText(f"Error: {text}")
        self.banner.show()

    def add_feed(self, source, text):
        self.feed.add(source, text, datetime.now().strftime("%H:%M:%S"))

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
            try:
                open_file(self._last_path)
            except OSError as e:
                dialogs.error(self, "Could not open the recording", str(e))

    def _show_folder(self):
        if self._last_path:
            try:
                show_in_explorer(self._last_path)
            except OSError as e:
                dialogs.error(self, "Could not show the file", str(e))
