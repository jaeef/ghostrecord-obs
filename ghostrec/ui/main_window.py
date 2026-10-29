"""Main window: navigation, OBS connection state, session orchestration.

Threading model (see plan §6): worker threads (session, connect/test) never
touch widgets. They push events into a queue that a QTimer drains on the GUI
thread.
"""

import queue
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QMainWindow, QMessageBox,
                             QPushButton, QStackedWidget, QSystemTrayIcon,
                             QVBoxLayout, QWidget)

from ghostrec.core import config as gcfg
from ghostrec.core.obs import (AudioWatcher, ObsError, connect, launch_obs,
                               test_connection, wait_for_port)
from ghostrec.core.recorder import RecorderSession
from ghostrec.ui import branding
from ghostrec.ui.pages.library import LibraryPage
from ghostrec.ui.pages.live import LivePage
from ghostrec.ui.pages.picker import PickerPage
from ghostrec.ui.pages.settings import SettingsPage
from ghostrec.ui.preview import PreviewWorker
from ghostrec.ui.tray import TrayIcon
from ghostrec.ui.widgets import StatusPill

PAGE_PICKER, PAGE_LIVE, PAGE_LIBRARY, PAGE_SETTINGS = range(4)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GhostRec OBS")
        self.setWindowIcon(branding.app_icon())
        self.resize(1000, 660)

        self.cfg = gcfg.validate_config(gcfg.load_config())
        self.req = None
        self.audio = None
        self.session = None
        self.preview_worker = None
        self.tray = None
        self._events = queue.Queue()
        self._manual_connect = False

        self._build_ui()
        self._build_tray()

        self._drain = QTimer(self)
        self._drain.setInterval(100)
        self._drain.timeout.connect(self._process_events)
        self._drain.start()

        self.library.set_folder(
            gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT))

        QTimer.singleShot(250, lambda: self._connect(manual=False))

    # ------------------------------------------------------------------ UI -- #

    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left sidebar container
        sidebar_box = QVBoxLayout()
        sidebar_box.setContentsMargins(0, 0, 0, 0)
        sidebar_box.setSpacing(0)

        brand_widget = QWidget()
        brand_widget.setStyleSheet("background: #090a0f; border-right: 1px solid #1a1d2b; padding: 18px 16px 12px 16px;")
        brand_lay = QVBoxLayout(brand_widget)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(2)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(0, 0, 0, 0)
        brand_row.setSpacing(10)
        brand_logo = QLabel()
        brand_logo.setPixmap(branding.logo_pixmap(30))
        brand_logo.setFixedSize(30, 30)
        brand_logo.setStyleSheet("background: transparent;")
        brand_logo.setToolTip("GhostRec OBS")

        brand_text = QVBoxLayout()
        brand_text.setContentsMargins(0, 0, 0, 0)
        brand_text.setSpacing(1)
        brand_lbl = QLabel("GhostRec")
        brand_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;")
        sub_lbl = QLabel("Window Lock • OBS")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748b; font-weight: 500;")
        brand_text.addWidget(brand_lbl)
        brand_text.addWidget(sub_lbl)

        brand_row.addWidget(brand_logo)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        brand_lay.addLayout(brand_row)
        sidebar_box.addWidget(brand_widget)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(190)
        for label in ("🎬  Record", "●  Live", "📁  Library", "⚙  Settings"):
            self.nav.addItem(QListWidgetItem(label))
        sidebar_box.addWidget(self.nav, 1)
        root.addLayout(sidebar_box)

        right = QVBoxLayout()
        right.setContentsMargins(20, 14, 20, 14)
        right.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 4)
        self.conn_pill = StatusPill("OBS offline", "err")
        self.connect_btn = QPushButton("Connect OBS")
        self.connect_btn.setStyleSheet("padding: 5px 14px; font-size: 12px;")
        header.addWidget(self.conn_pill)
        header.addStretch(1)
        header.addWidget(self.connect_btn)
        right.addLayout(header)

        self.stack = QStackedWidget()
        self.picker = PickerPage()
        self.live = LivePage()
        self.library = LibraryPage()
        self.settings = SettingsPage()
        for page in (self.picker, self.live, self.library, self.settings):
            self.stack.addWidget(page)
        right.addWidget(self.stack, 1)
        root.addLayout(right, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(PAGE_PICKER)

        self.connect_btn.clicked.connect(self._on_connect_clicked)
        self.picker.record_requested.connect(self._start_recording)
        self.live.stop_requested.connect(self._stop_recording)
        self.live.back_requested.connect(lambda: self._show_page(PAGE_PICKER))
        self.settings.test_requested.connect(self._do_test_connection)
        self.settings.launch_obs_requested.connect(self._do_launch_obs)
        self.settings.save_requested.connect(self._save_settings)
        self.settings.load_from(self.cfg)

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = TrayIcon(self, on_stop=self._stop_recording,
                             on_quit=self._quit)

    def _on_nav(self, row):
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        if row == PAGE_LIBRARY:
            self.library.refresh()
        elif row == PAGE_SETTINGS:
            self.settings.load_from(self.cfg)

    def _show_page(self, page):
        self.nav.setCurrentRow(page)

    # ------------------------------------------------------------ connect -- #

    def _on_connect_clicked(self):
        if self.req is not None:
            self._disconnect()
        else:
            self._connect(manual=True)

    def _connect(self, manual):
        if self.req is not None:
            return
        self._manual_connect = manual
        self.conn_pill.set_state("warn", "connecting…")
        self.connect_btn.setEnabled(False)
        threading.Thread(target=self._connect_worker, daemon=True).start()

    def _connect_worker(self):
        try:
            req = connect(self.cfg)
            ver = req.get_version().obs_version
        except ObsError as e:
            self._events.put(("connect_failed", str(e)))
            return
        watcher = None
        audio_err = ""
        if self.cfg.get("audio", {}).get("check"):
            watcher = AudioWatcher(self.cfg)
            ok, audio_err = watcher.start(self.cfg["obs"]["host"],
                                          self.cfg["obs"]["port"],
                                          self.cfg["obs"]["password"])
            if not ok:
                watcher = None
        self._events.put(("connected", req, ver, watcher, audio_err))

    def _handle_connected(self, req, ver, watcher, audio_err):
        self.req = req
        self.audio = watcher
        self.conn_pill.set_state("ok", f"OBS {ver} connected")
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        if audio_err:
            self.live.add_feed("audio", audio_err)
            if self.tray:
                self.tray.notify("GhostRec", audio_err, warn=True)

    def _handle_connect_failed(self, msg):
        self.conn_pill.set_state("err", "OBS offline")
        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)
        self.conn_pill.setToolTip(msg)
        if self._manual_connect:
            QMessageBox.warning(self, "Connection failed", msg)

    def _disconnect(self):
        if self.session and self.session.is_running:
            QMessageBox.information(self, "Recording",
                                    "Stop the recording first.")
            return
        self._stop_preview()
        if self.audio:
            self.audio.stop()
        self.audio = None
        self.req = None
        self.conn_pill.set_state("err", "OBS offline")
        self.conn_pill.setToolTip("")
        self.connect_btn.setText("Connect")

    # ----------------------------------------------------------- recording -- #

    def _start_recording(self, win, name):
        if self.session and self.session.is_running:
            return
        if self.req is None:
            QMessageBox.warning(self, "Not connected",
                                "Connect to OBS first (Connect button or "
                                "Settings).")
            return
        out_dir = gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT)
        self.picker.set_busy(True)
        self.live.begin_session()
        self.session = RecorderSession(
            self.req, self.cfg, win, name, self.audio, out_dir,
            emit=lambda ev: self._events.put(("session", ev)))
        self.session.start()
        self._start_preview()
        self._show_page(PAGE_LIVE)

    def _start_preview(self):
        self._stop_preview()
        self.preview_worker = PreviewWorker(
            self.cfg, self.cfg["capture_scene_name"],
            emit=lambda item: self._events.put(item))
        self.preview_worker.start()

    def _stop_preview(self):
        if self.preview_worker:
            self.preview_worker.stop()
            self.preview_worker = None

    def _stop_recording(self):
        if self.session and self.session.is_running:
            self.session.request_stop()

    def _handle_session_event(self, ev):
        t = ev.get("type")
        if t == "note":
            self.live.add_feed(ev.get("source", "?"), ev.get("text", ""))
        elif t == "started":
            self.live.on_started(ev)
            if self.tray:
                self.tray.set_recording(True)
                self.tray.notify("Recording started",
                                 f"{ev.get('name', '')} — "
                                 f"{ev.get('window_title', '')}")
        elif t == "tick":
            self.live.on_tick(ev)
            if self.tray:
                self.tray.update_elapsed(ev.get("elapsed", 0.0))
        elif t == "warning":
            if self.tray:
                self.tray.notify("GhostRec warning", ev.get("text", ""),
                                 warn=True)
        elif t == "stopping":
            self.live.on_stopping(ev)
        elif t == "stopped":
            self._stop_preview()
            self.live.on_stopped(ev)
            self.picker.set_busy(False)
            if ev.get("final_path"):
                self.library.mark_recent(ev["final_path"],
                                         ev.get("duration", 0.0))
            else:
                self.library.refresh()
            if self.tray:
                self.tray.set_recording(False)
                if ev.get("final_path"):
                    import os
                    self.tray.notify("Recording saved",
                                     os.path.basename(ev["final_path"]))
                elif ev.get("timed_out"):
                    self.tray.notify("Recording",
                                     "File finalization timed out — check "
                                     "OBS's recording folder.", warn=True)
        elif t == "aborted":
            self._stop_preview()
            self.live.on_aborted(ev.get("reason", ""))
            self.picker.set_busy(False)
            if self.tray:
                self.tray.notify("Recording aborted", ev.get("reason", ""),
                                 warn=True)
        elif t == "error":
            self._stop_preview()
            self.live.on_error(ev.get("text", ""))
            self.picker.set_busy(False)
            if self.tray:
                self.tray.set_recording(False)
                self.tray.notify("GhostRec error", ev.get("text", ""),
                                 warn=True)
        # "finished": nothing further — flags were already reset above.

    # ------------------------------------------------------------ settings -- #

    def _do_test_connection(self, host, port, password):
        def work():
            try:
                ver = test_connection(host, port, password)
                self._events.put(("test_result", True,
                                  f"Connected to OBS {ver}."))
            except ObsError as e:
                self._events.put(("test_result", False, str(e)))
        threading.Thread(target=work, daemon=True).start()

    def _do_launch_obs(self, port):
        def work():
            if launch_obs():
                ok = wait_for_port(port, timeout=30)
                self._events.put((
                    "launch_result", ok,
                    "OBS is up and the WebSocket port is listening."
                    if ok else "Port not listening after 30s — check OBS "
                               "WebSocket settings."))
            else:
                self._events.put(("launch_result", False,
                                  "OBS not found in the default install "
                                  "location — start it manually."))
        threading.Thread(target=work, daemon=True).start()

    def _save_settings(self, new_cfg):
        old_obs = dict(self.cfg.get("obs", {}))
        self.cfg = gcfg.validate_config(new_cfg)
        gcfg.save_config(self.cfg)
        self.settings.show_saved()
        self.library.set_folder(
            gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT))
        if self.req is not None and dict(self.cfg.get("obs", {})) != old_obs:
            # Credentials/port changed — reconnect in the background.
            self._disconnect()
            self._connect(manual=False)

    # --------------------------------------------------------------- queue -- #

    def _process_events(self):
        while True:
            try:
                item = self._events.get_nowait()
            except queue.Empty:
                return
            kind = item[0]
            if kind == "connected":
                self._handle_connected(*item[1:])
            elif kind == "connect_failed":
                self._handle_connect_failed(item[1])
            elif kind == "session":
                self._handle_session_event(item[1])
            elif kind == "test_result":
                self.settings.show_test_result(item[1], item[2])
            elif kind == "launch_result":
                self.settings.show_launch_result(item[1], item[2])
            elif kind == "preview":
                self.live.set_preview(item[1])
            elif kind == "preview_error":
                self.live.set_preview_error(item[1])

    # ------------------------------------------------------------- closing -- #

    def closeEvent(self, event):
        if self.session and self.session.is_running:
            self.hide()
            if self.tray:
                self.tray.notify("GhostRec", "Still recording — the app "
                                             "keeps running in the tray.",
                                 warn=True)
            event.ignore()
            return
        self._quit()
        event.accept()

    def _quit(self):
        if self.session and self.session.is_running:
            QMessageBox.information(self, "Recording in progress",
                                    "Stop the recording first (Live page → "
                                    "Stop & save).")
            return
        if self.audio:
            self.audio.stop()
        self._stop_preview()
        if self.tray:
            self.tray.hide()
        QApplication.quit()
