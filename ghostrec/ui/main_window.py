"""Main window: navigation, OBS connection state, session orchestration.

Threading model (see plan §6): worker threads (session, connect/test) never
touch widgets. They push events into a queue that a QTimer drains on the GUI
thread.
"""

import copy
import queue
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QMainWindow,
                             QPushButton, QStackedWidget, QSystemTrayIcon,
                             QVBoxLayout, QWidget)

from ghostrec.core import config as gcfg
from ghostrec.core import safe_apps
from ghostrec.core.apps import launch_record_chrome
from ghostrec.core.obs import (AudioWatcher, connect, launch_obs,
                               test_connection, wait_for_port)
from ghostrec.core.recorder import RecorderSession
from ghostrec.ui import branding, chrome, dialogs, theme
from ghostrec.ui.pages.library import LibraryPage
from ghostrec.ui.pages.live import LivePage
from ghostrec.ui.pages.picker import PickerPage
from ghostrec.ui.pages.settings import SettingsPage
from ghostrec.ui.preview import PreviewWorker
from ghostrec.ui.tray import TrayIcon
from ghostrec.ui.widgets import StatusPill

PAGE_PICKER, PAGE_LIVE, PAGE_LIBRARY, PAGE_SETTINGS = range(4)

# (sidebar label, icon, toolbar title, toolbar subtitle)
PAGES = (
    ("Record", "record", "Record a window",
     "Pick one restored window — only that window is captured"),
    ("Live", "live", "Live session",
     "Watch the capture while you keep working"),
    ("Library", "library", "Recordings", "Finished files, newest first"),
    ("Settings", "settings", "Settings",
     "OBS connection, capture, output and appearance"),
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GhostRec OBS")
        self.setWindowIcon(branding.app_icon())
        gcfg.ensure_config()
        self.cfg = gcfg.validate_config(gcfg.load_config())
        self._capture_state = None   # None | "rec" | "warn"
        self.resize(1180, 780)
        self.setMinimumSize(980, 680)
        self.req = None
        self.audio = None
        self.session = None
        self.preview_worker = None
        self._preview_generation = 0
        self.tray = None
        self._events = queue.Queue()
        self._manual_connect = False
        self._connect_generation = 0
        self._previewing_appearance = False

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

        # ---- sidebar (source list) ---------------------------------------
        sidebar = QWidget()
        sidebar.setObjectName("sidebarPane")
        sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(0)

        side.addSpacing(16)

        section = QLabel("GhostRec")
        section.setObjectName("sidebarSection")
        section_row = QHBoxLayout()
        section_row.setContentsMargins(16, 0, 16, 4)
        section_row.addWidget(section)
        side.addLayout(section_row)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebar")
        self.nav.setIconSize(chrome.ICON_SIZE)
        self.nav.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for label, *_ in PAGES:
            self.nav.addItem(QListWidgetItem(label))
        self._refresh_nav_icons()
        side.addWidget(self.nav, 1)

        footer = QWidget()
        footer.setObjectName("sidebarFooter")
        footer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(16, 10, 16, 14)
        footer_lay.setSpacing(10)
        brand_logo = QLabel()
        brand_logo.setPixmap(branding.logo_pixmap(28))
        brand_logo.setFixedSize(28, 28)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_lbl = QLabel("GhostRec")
        brand_lbl.setObjectName("brandTitle")
        from ghostrec import __version__
        sub_lbl = QLabel(f"Version {__version__} · for OBS")
        sub_lbl.setObjectName("brandSubtitle")
        brand_text.addWidget(brand_lbl)
        brand_text.addWidget(sub_lbl)
        footer_lay.addWidget(brand_logo)
        footer_lay.addLayout(brand_text, 1)
        side.addWidget(footer)
        root.addWidget(sidebar)

        # ---- content: unified toolbar + pages ------------------------------
        content = QWidget()
        content.setObjectName("contentPane")
        right = QVBoxLayout(content)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        toolbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        toolbar.setFixedHeight(56)
        header = QHBoxLayout(toolbar)
        header.setContentsMargins(22, 0, 16, 0)
        header.setSpacing(10)
        header_text = QVBoxLayout()
        header_text.setSpacing(0)
        header_text.addStretch(1)
        self.toolbar_title = QLabel(PAGES[0][2])
        self.toolbar_title.setObjectName("toolbarTitle")
        self.toolbar_subtitle = QLabel(PAGES[0][3])
        self.toolbar_subtitle.setObjectName("toolbarSubtitle")
        header_text.addWidget(self.toolbar_title)
        header_text.addWidget(self.toolbar_subtitle)
        header_text.addStretch(1)
        header.addLayout(header_text)
        header.addStretch(1)
        self.conn_pill = StatusPill("OBS offline", "err")
        self.connect_btn = QPushButton("Connect OBS")
        header.addWidget(self.conn_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.connect_btn)
        right.addWidget(toolbar)

        body = QVBoxLayout()
        body.setContentsMargins(24, 18, 24, 20)
        self.stack = QStackedWidget()
        self.picker = PickerPage()
        self.live = LivePage()
        self.library = LibraryPage()
        self.settings = SettingsPage()
        for page in (self.picker, self.live, self.library, self.settings):
            self.stack.addWidget(page)
        body.addWidget(self.stack, 1)
        right.addLayout(body, 1)
        root.addWidget(content, 1)
        self.setCentralWidget(central)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.nav.setCurrentRow(PAGE_PICKER)

        self.connect_btn.clicked.connect(self._on_connect_clicked)
        self.picker.record_requested.connect(self._start_recording)
        self.picker.chrome_requested.connect(self._launch_isolated_chrome)
        self.picker.make_safe_requested.connect(self._make_safe)
        self.picker.connect_requested.connect(
            lambda: self._connect(manual=True))
        self.live.stop_requested.connect(self._stop_recording)
        self.live.library_requested.connect(lambda: self._show_page(PAGE_LIBRARY))
        self.live.capture_source_requested.connect(self._set_capture_source)
        self.live.record_chrome_requested.connect(self._make_session_app_safe)
        self.live.isolated_chrome_requested.connect(self._launch_isolated_chrome)
        self.settings.test_requested.connect(self._do_test_connection)
        self.settings.launch_obs_requested.connect(self._do_launch_obs)
        self.settings.save_requested.connect(self._save_settings)
        self.settings.appearance_changed.connect(self._set_appearance)
        hints = QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(
                lambda *_: self._set_appearance(None))
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

    # -------------------------------------------------------- appearance -- #

    def _refresh_nav_icons(self):
        for i, (_, icon, *_rest) in enumerate(PAGES):
            item = self.nav.item(i)
            if item is not None:
                # neutral icons; the current page gets the accent, and Live
                # turns red while recording (OBS-style)
                color = (theme.ERR if icon == "live" and self._capture_state
                         else theme.ACCENT_FG if i == self.nav.currentRow()
                         else theme.MUTED)
                item.setIcon(chrome.glyph_icon(icon, color))

    def _set_appearance(self, appearance):
        """Re-theme the running app. None = re-resolve the saved preference."""
        if appearance is None:
            appearance = self.cfg.get("ui", {}).get("appearance", "auto")
            if appearance != "auto":
                return  # explicit choice ignores OS theme changes
        saved = self.cfg.get("ui", {}).get("appearance", "auto")
        self._previewing_appearance = appearance != saved
        mode = theme.apply(QApplication.instance(), appearance)
        self._refresh_nav_icons()
        for pill in self.findChildren(StatusPill):
            pill.restyle()
        self.picker.restyle()
        self.live.restyle()
        chrome.style_window(self)

    def showEvent(self, event):
        super().showEvent(event)
        chrome.style_window(self)

    def _set_capture_state(self, state):
        """OBS-style cue on the logo: red dot while recording, yellow dot
        when the recording is at risk (see live.capture_health). Shows in the
        title bar, the taskbar and the tray."""
        if state == self._capture_state:
            return
        self._capture_state = state
        icon = branding.status_icon(state) if state else branding.app_icon()
        self.setWindowIcon(icon)
        if self.tray:
            self.tray.setIcon(branding.status_icon(state))
        self._refresh_nav_icons()

    def _on_nav(self, row):
        if row < 0:
            return
        self.stack.setCurrentIndex(row)
        self._refresh_nav_icons()
        self.toolbar_title.setText(PAGES[row][2])
        self.toolbar_subtitle.setText(PAGES[row][3])
        if row != PAGE_SETTINGS and self._previewing_appearance:
            # leaving Settings without saving reverts an appearance preview
            self._set_appearance(self.cfg.get("ui", {}).get("appearance",
                                                            "auto"))
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
        self.picker.set_obs_connected(True)
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        if audio_err:
            self.live.add_feed("audio", audio_err)
            if self.tray:
                self.tray.notify("GhostRec", audio_err, warn=True)

    def _handle_connect_failed(self, token, msg):
        if token != self._connect_generation:
            return
        self.picker.set_obs_connected(False)
        self.conn_pill.set_state("err", "OBS offline")
        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)
        self.conn_pill.setToolTip(msg)
        if self._manual_connect:
            dialogs.error(self, "Could not connect to OBS", msg)

    def _disconnect(self):
        if self.session and self.session.is_running:
            dialogs.info(self, "Recording in progress",
                         "Stop the recording before disconnecting from OBS.")
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
        self.picker.set_obs_connected(False)
        self.conn_pill.set_state("err", "OBS offline")
        self.conn_pill.setToolTip("")
        self.connect_btn.setText("Connect")

    # ----------------------------------------------------------- recording -- #

    def _start_recording(self, win, name):
        if self.session and self.session.is_running:
            return
        if self.req is None:
            dialogs.warn(self, "OBS is not connected",
                         "Open OBS Studio, then click Connect in the toolbar.")
            return
        if self._needs_safe_preflight(win):
            name = safe_apps.app_name(win.get("exe"))
            choice = dialogs.alert(
                self, f"{name} may freeze while covered",
                f"{name} stops drawing when another window covers it, so the "
                "recording would freeze. Restart it once in recording-safe "
                "mode, then select its window again.",
                [("Make Recording-Safe", "primary"),
                 ("Record Anyway", "normal"),
                 ("Cancel", "cancel")],
                kind="warning")
            if choice == "Make Recording-Safe":
                self._make_safe(win)
                return
            if choice != "Record Anyway":
                return
        out_dir = gcfg.resolve_output_folder(self.cfg, gcfg.REPO_ROOT)
        self._session_win = dict(win)
        self.picker.set_busy(True)
        self.live.begin_session()
        self.session = RecorderSession(
            self.req, copy.deepcopy(self.cfg), win, name, self.audio, out_dir,
            emit=lambda ev: self._events.put(("session", ev)))
        self.session.start()
        self._start_preview()
        self._show_page(PAGE_LIVE)

    def _needs_safe_preflight(self, win):
        if not self.cfg.get("capture", {}).get("auto", True):
            return False
        return (bool(safe_apps.app_kind(win.get("exe")))
                and not win.get("record_friendly", False))

    def _make_safe(self, win, force=False):
        """Restart the window's app in recording-safe mode (asks first)."""
        if self.session and self.session.is_running:
            dialogs.info(
                self, "Recording in progress",
                "Stop the recording first. Restarting the app would close "
                "the window being recorded.")
            return
        if not force:
            message, detail = safe_apps.describe_restart(win)
            name = safe_apps.app_name(win.get("exe"))
            if not dialogs.confirm(
                    self, f"Restart {name} in recording-safe mode?", message,
                    ok="Restart", detail=detail):
                return
        self.picker.set_busy(True)
        self.picker.start_btn.setText("Restarting app…")

        def work():
            try:
                status, msg = safe_apps.make_recording_safe(win, force=force)
            except Exception as e:
                status, msg = "error", str(e)
            self._events.put(("make_safe_result", status, msg, win))

        threading.Thread(target=work, name="ghostrec-make-safe",
                         daemon=True).start()

    def _make_session_app_safe(self):
        win = getattr(self, "_session_win", None)
        if win:
            self._make_safe(win)

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
            self._set_capture_state("rec")
            self.live.on_started(ev)
            if self.tray:
                self.tray.set_recording(True)
                self.tray.notify("Recording started",
                                 f"{ev.get('name', '')} — "
                                 f"{ev.get('window_title', '')}")
        elif t == "tick":
            self.live.on_tick(ev)
            self._set_capture_state(self.live.capture_state)
            if self.tray:
                self.tray.update_elapsed(ev.get("elapsed", 0.0))
        elif t == "warning":
            self.live.add_feed("warn", ev.get("text", ""))
            if self.tray:
                self.tray.notify("GhostRec warning", ev.get("text", ""),
                                 warn=True)
        elif t == "stopping":
            self._set_capture_state(None)
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
            self._set_capture_state(None)
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
            dialogs.info(
                self, "Recording in progress",
                "Stop the current recording before changing settings.")
            return
        old_obs = dict(self.cfg.get("obs", {}))
        try:
            self.cfg = gcfg.validate_config(new_cfg)
            gcfg.save_config(self.cfg)
        except (OSError, ValueError) as e:
            dialogs.error(self, "Settings not saved", str(e))
            return
        self.settings.show_saved()
        self._set_appearance(self.cfg.get("ui", {}).get("appearance", "auto"))
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
            elif kind == "make_safe_result":
                status, msg, win = item[1], item[2], item[3]
                self.picker.set_busy(False)
                if status == "needs_force":
                    if dialogs.confirm(self, "Still running in the background",
                                       msg, ok="Quit & Restart",
                                       destructive=True, kind="warning"):
                        self._make_safe(win, force=True)
                    continue
                if status == "done":
                    self.live.add_feed("apps", msg)
                    QTimer.singleShot(2500, self.picker.refresh)
                    dialogs.info(self, "Ready to record", msg,
                                 kind="success")
                else:
                    dialogs.error(self, "Could not make it recording-safe",
                                  msg)
                self.settings.refresh_webview2_state()
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
                dialogs.info(
                    self, "Recording in progress",
                    "Stop the recording before closing GhostRec. No system "
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
            dialogs.info(self, "Recording in progress",
                         "Stop the recording first (Live → Stop & Save).")
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
