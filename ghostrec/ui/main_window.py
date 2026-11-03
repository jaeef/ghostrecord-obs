"""Main window: navigation, OBS connection state, session orchestration.

Threading model (see plan §6): worker threads (session, connect/test) never
touch widgets. They push events into a queue that a QTimer drains on the GUI
thread.
"""

import copy
import queue
import threading

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QMainWindow, QMessageBox,
                             QPushButton, QStackedWidget, QSystemTrayIcon,
                             QVBoxLayout, QWidget)

from ghostrec.core import config as gcfg
from ghostrec.core.apps import (is_throttle_prone, launch_record_chrome,
                                relaunch_chrome_with_flags)
from ghostrec.core.obs import (AudioWatcher, connect, launch_obs,
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
        self.resize(1180, 780)
        self.setMinimumSize(980, 680)

        gcfg.ensure_config()
        self.cfg = gcfg.validate_config(gcfg.load_config())
        self.req = None
        self.audio = None
        self.session = None
        self.preview_worker = None
        self._preview_generation = 0
        self.tray = None
        self._events = queue.Queue()
        self._manual_connect = False
        self._connect_generation = 0

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
        central.setObjectName("centralWidget")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left sidebar container
        sidebar_box = QVBoxLayout()
        sidebar_box.setContentsMargins(0, 0, 0, 0)
        sidebar_box.setSpacing(0)

        brand_widget = QWidget()
        brand_widget.setObjectName("brandPanel")
        brand_lay = QVBoxLayout(brand_widget)
        brand_lay.setContentsMargins(20, 20, 20, 18)
        brand_lay.setSpacing(3)

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
        brand_lbl.setObjectName("brandTitle")
        sub_lbl = QLabel("Focused capture for OBS")
        sub_lbl.setObjectName("brandSubtitle")
        brand_text.addWidget(brand_lbl)
        brand_text.addWidget(sub_lbl)

        brand_row.addWidget(brand_logo)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        brand_lay.addLayout(brand_row)
        sidebar_box.addWidget(brand_widget)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setFixedWidth(216)
        for label in ("Record", "Live", "Library", "Settings"):
            self.nav.addItem(QListWidgetItem(label))
        sidebar_box.addWidget(self.nav, 1)

        sidebar_footer = QWidget()
        sidebar_footer.setObjectName("sidebarFooter")
        footer_lay = QVBoxLayout(sidebar_footer)
        footer_lay.setContentsMargins(20, 14, 20, 16)
        footer_lay.setSpacing(3)
        footer_title = QLabel("Window lock")
        footer_title.setObjectName("sidebarHint")
        footer_note = QLabel("One target • no desktop capture")
        footer_note.setObjectName("sidebarHint")
        footer_lay.addWidget(footer_title)
        footer_lay.addWidget(footer_note)
        sidebar_box.addWidget(sidebar_footer)
        root.addLayout(sidebar_box)

        right = QVBoxLayout()
        right.setContentsMargins(28, 22, 28, 22)
        right.setSpacing(18)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        header_title = QLabel("Recording workspace")
        header_title.setObjectName("headerTitle")
        header_subtitle = QLabel("Capture one restored window while you work in another")
        header_subtitle.setObjectName("headerSubtitle")
        header_text.addWidget(header_title)
        header_text.addWidget(header_subtitle)
        header.addLayout(header_text)
        header.addStretch(1)
        self.conn_pill = StatusPill("OBS offline", "err")
        self.connect_btn = QPushButton("Connect OBS")
        self.connect_btn.setObjectName("secondary")
        header.addWidget(self.conn_pill)
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
        self.picker.chrome_requested.connect(self._launch_isolated_chrome)
        self.live.stop_requested.connect(self._stop_recording)
        self.live.back_requested.connect(lambda: self._show_page(PAGE_PICKER))
        self.live.library_requested.connect(lambda: self._show_page(PAGE_LIBRARY))
        self.live.capture_source_requested.connect(self._set_capture_source)
        self.live.record_chrome_requested.connect(self._relaunch_chrome)
        self.live.isolated_chrome_requested.connect(self._launch_isolated_chrome)
        self.settings.test_requested.connect(self._do_test_connection)
        self.settings.launch_obs_requested.connect(self._do_launch_obs)
        self.settings.save_requested.connect(self._save_settings)
        self.settings.load_from(self.cfg)
        self.picker.set_output_dir(
            gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT))
        self.live.set_capture_source(self.cfg.get("capture", {}).get(
            "source", "window"))
        self.live.set_silence_limit(self.cfg.get("audio", {}).get(
            "silence_alert_seconds", 30))

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
        self._connect_generation += 1
        token = self._connect_generation
        self._manual_connect = manual
        self.conn_pill.set_state("warn", "connecting…")
        self.connect_btn.setEnabled(False)
        threading.Thread(target=self._connect_worker, args=(token,),
                         daemon=True).start()

    def _connect_worker(self, token):
        cfg = copy.deepcopy(self.cfg)
        try:
            req = connect(cfg)
            ver = req.get_version().obs_version
        except Exception as e:
            self._events.put(("connect_failed", token, str(e)))
            return
        watcher = None
        audio_err = ""
        if cfg.get("audio", {}).get("check"):
            watcher = AudioWatcher(cfg)
            ok, audio_err = watcher.start(cfg["obs"]["host"],
                                          cfg["obs"]["port"],
                                          cfg["obs"]["password"])
            if not ok:
                watcher.stop()
                watcher = None
        self._events.put(("connected", token, req, ver, watcher, audio_err))

    def _handle_connected(self, token, req, ver, watcher, audio_err):
        if token != self._connect_generation or self.req is not None:
            if watcher:
                watcher.stop()
            disconnect = getattr(req, "disconnect", None)
            if disconnect:
                try:
                    disconnect()
                except Exception:
                    pass
            return
        self.req = req
        self.audio = watcher
        self.conn_pill.set_state("ok", f"OBS {ver} connected")
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        if audio_err:
            self.live.add_feed("audio", audio_err)
            if self.tray:
                self.tray.notify("GhostRec", audio_err, warn=True)

    def _handle_connect_failed(self, token, msg):
        if token != self._connect_generation:
            return
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
        self._connect_generation += 1
        self._stop_preview()
        if self.audio:
            self.audio.stop()
        self.audio = None
        if self.req:
            disconnect = getattr(self.req, "disconnect", None)
            if disconnect:
                try:
                    disconnect()
                except Exception:
                    pass
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
        if self._needs_browser_preflight(win):
            answer = QMessageBox.question(
                self,
                "Prepare covered-window capture",
                "This Chrome window is not running with anti-occlusion flags.\n\n"
                "Modern WGC will isolate the window from other apps, but "
                "Chrome itself may stop painting when fully covered. Restart "
                "Chrome with recording-safe flags and restore its tabs before "
                "you select the target again?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._restart_safe_browser_for_pick()
                return
        out_dir = gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT)
        self.picker.set_busy(True)
        self.live.begin_session()
        self.session = RecorderSession(
            self.req, copy.deepcopy(self.cfg), win, name, self.audio, out_dir,
            emit=lambda ev: self._events.put(("session", ev)))
        self.session.start()
        self._start_preview()
        self._show_page(PAGE_LIVE)

    def _needs_browser_preflight(self, win):
        capture = self.cfg.get("capture", {})
        if not capture.get("auto", True):
            return False
        exe = (win.get("exe") or "").lower()
        return (exe == "chrome.exe" and is_throttle_prone(exe)
                and not win.get("record_friendly", False))

    def _restart_safe_browser_for_pick(self):
        self.picker.set_busy(True)

        def work():
            ok, msg = relaunch_chrome_with_flags()
            self._events.put(("safe_browser_result", ok, msg))

        threading.Thread(target=work, name="ghostrec-safe-browser",
                         daemon=True).start()

    def _start_preview(self):
        self._stop_preview()
        self._preview_generation = getattr(self, "_preview_generation", 0) + 1
        self.preview_worker = PreviewWorker(
            self.cfg, self.cfg["capture_scene_name"],
            emit=lambda item: self._events.put(item),
            token=self._preview_generation)
        self.preview_worker.start()

    def _stop_preview(self):
        self._preview_generation += 1
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
        elif t == "capture_advice":
            self.live.on_capture_advice(ev)
        elif t == "relocked":
            self.live.on_relocked(ev)
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
            self.live.add_feed("warn", ev.get("text", ""))
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
        elif t == "finished":
            self.session = None

    # -------------------------------------------------------- quick actions -- #

    def _set_capture_source(self, source):
        if source not in ("window", "game"):
            return
        if self.session and self.session.is_running:
            current = self.cfg.get("capture", {}).get("source", "window")
            self.live.set_capture_source(current)
            self.live.add_feed(
                "settings", "capture source changes apply after recording")
            return
        self.cfg.setdefault("capture", {})["source"] = source
        try:
            gcfg.save_config(self.cfg)
            self.settings.load_from(self.cfg)
            self.live.set_capture_source(source)
        except (OSError, ValueError) as e:
            self.live.add_feed("error", f"could not save capture setting: {e}")

    def _launch_isolated_chrome(self):
        def work():
            ok, msg = launch_record_chrome()
            self._events.put(("app_action", ok, msg))
        threading.Thread(target=work, daemon=True).start()

    def _relaunch_chrome(self):
        if self.session and self.session.is_running:
            self.live.add_feed(
                "apps", "cannot restart Chrome during recording; "
                "use Isolated Chrome for the next recording")
            return

        def work():
            ok, msg = relaunch_chrome_with_flags()
            self._events.put(("app_action", ok, msg))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ settings -- #

    def _do_test_connection(self, host, port, password):
        def work():
            try:
                ver = test_connection(host, port, password)
                self._events.put(("test_result", True,
                                  f"Connected to OBS {ver}."))
            except Exception as e:
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
        if self.session and self.session.is_running:
            QMessageBox.information(
                self, "Recording in progress",
                "Stop the current recording before changing settings.")
            return
        old_obs = dict(self.cfg.get("obs", {}))
        try:
            self.cfg = gcfg.validate_config(new_cfg)
            gcfg.save_config(self.cfg)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Settings not saved", str(e))
            return
        self.settings.show_saved()
        self.library.set_folder(
            gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT))
        self.picker.set_output_dir(
            gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT))
        self.live.set_capture_source(self.cfg.get("capture", {}).get(
            "source", "window"))
        self.live.set_silence_limit(self.cfg.get("audio", {}).get(
            "silence_alert_seconds", 30))
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
                self._handle_connect_failed(item[1], item[2])
            elif kind == "session":
                self._handle_session_event(item[1])
            elif kind == "test_result":
                self.settings.show_test_result(item[1], item[2])
            elif kind == "launch_result":
                self.settings.show_launch_result(item[1], item[2])
            elif kind == "app_action":
                ok, msg = item[1], item[2]
                self.live.add_feed("apps", msg)
                if self.tray:
                    self.tray.notify("GhostRec", msg, warn=not ok)
            elif kind == "safe_browser_result":
                ok, msg = item[1], item[2]
                self.picker.set_busy(False)
                self.picker.refresh()
                if ok:
                    QMessageBox.information(
                        self, "Browser ready",
                        f"{msg}\n\nSelect the restored Chrome window and "
                        "start the recording again.")
                else:
                    QMessageBox.warning(self, "Browser not prepared", msg)
            elif kind == "preview":
                if len(item) >= 3 and item[1] == getattr(
                        self, "_preview_generation", 0):
                    self.live.set_preview(item[2])
            elif kind == "preview_error":
                if len(item) >= 3 and item[1] == getattr(
                        self, "_preview_generation", 0):
                    self.live.set_preview_error(item[2])

    # ------------------------------------------------------------- closing -- #

    def closeEvent(self, event):
        if self.session and self.session.is_running:
            if not self.tray:
                self._show_page(PAGE_LIVE)
                QMessageBox.information(
                    self, "Recording in progress",
                    "Stop the recording before closing GhostRec; no system "
                    "tray is available to keep it running.")
                event.ignore()
                return
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
        if self.req:
            disconnect = getattr(self.req, "disconnect", None)
            if disconnect:
                try:
                    disconnect()
                except Exception:
                    pass
        self._stop_preview()
        if self.tray:
            self.tray.hide()
        QApplication.quit()
