"""Settings page: OBS connection, output folder, audio thresholds."""

import copy

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QFrame, QGroupBox,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ghostrec.ui import theme


def _form(box):
    """macOS-style form: right-aligned labels, roomy rows."""
    form = QFormLayout(box)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(10)
    return form


class SettingsPage(QWidget):
    test_requested = pyqtSignal(str, int, str)  # host, port, password
    launch_obs_requested = pyqtSignal(int)      # port
    save_requested = pyqtSignal(dict)           # full config dict
    appearance_changed = pyqtSignal(str)        # "auto" | "light" | "dark"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = {}
        self._loading = False

        # The form is taller than the window: scroll it, keep Save visible.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setMaximumWidth(760)
        root = QVBoxLayout(inner)
        root.setContentsMargins(0, 0, 12, 0)
        holder = QWidget()
        holder_lay = QHBoxLayout(holder)
        holder_lay.setContentsMargins(0, 0, 0, 0)
        holder_lay.addStretch(1)
        holder_lay.addWidget(inner, 100)
        holder_lay.addStretch(1)
        scroll.setWidget(holder)
        outer.addWidget(scroll, 1)

        # -- Appearance --------------------------------------------------------
        look_box = QGroupBox("Appearance")
        look_form = _form(look_box)
        self.appearance_combo = QComboBox()
        self.appearance_combo.addItem("Automatic (follow Windows)", "auto")
        self.appearance_combo.addItem("Light", "light")
        self.appearance_combo.addItem("Dark", "dark")
        look_form.addRow("Appearance:", self.appearance_combo)
        self.native_frame = QCheckBox(
            "Use the standard Windows title bar (restart to apply)")
        look_form.addRow("", self.native_frame)
        root.addWidget(look_box)
        self.appearance_combo.currentIndexChanged.connect(
            self._emit_appearance)

        # -- OBS -------------------------------------------------------------
        obs_box = QGroupBox("OBS WebSocket")
        form = _form(obs_box)
        self.host_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        password_row = QHBoxLayout()
        password_row.setSpacing(8)
        self.pwd_edit = QLineEdit()
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_pwd = QPushButton("Show")
        self.show_pwd.setCheckable(True)
        self.show_pwd.setFixedWidth(60)
        self.show_pwd.toggled.connect(self._toggle_pwd)
        password_row.addWidget(self.pwd_edit, 1)
        password_row.addWidget(self.show_pwd)
        form.addRow("Host:", self.host_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("Password:", password_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.test_btn = QPushButton("Test Connection")
        self.launch_btn = QPushButton("Launch OBS")
        buttons.addWidget(self.test_btn)
        buttons.addWidget(self.launch_btn)
        buttons.addStretch(1)
        form.addRow("", buttons)

        self.test_label = QLabel("")
        self.test_label.setObjectName("muted")
        self.test_label.setWordWrap(True)
        form.addRow("", self.test_label)
        root.addWidget(obs_box)

        # -- Scene & source ---------------------------------------------------
        scene_box = QGroupBox("Scene && source")
        scene_form = _form(scene_box)
        self.scene_edit = QLineEdit()
        self.source_edit = QLineEdit()
        scene_form.addRow("Scene name:", self.scene_edit)
        scene_form.addRow("Capture source name:", self.source_edit)
        scene_hint = QLabel("GhostRec creates a dedicated scene containing only "
                            "the window capture source — your other scenes are "
                            "never touched, and the full display is never captured.")
        scene_hint.setObjectName("muted")
        scene_hint.setWordWrap(True)
        scene_form.addRow("", scene_hint)
        root.addWidget(scene_box)

        # -- Capture ---------------------------------------------------------------
        cap_box = QGroupBox("Capture")
        cap_form = _form(cap_box)
        self.source_combo = QComboBox()
        self.source_combo.addItem(
            "Window Capture — Modern WGC for covered windows", "window")
        self.source_combo.addItem(
            "Game Capture — only for apps with OBS game hooks", "game")
        cap_form.addRow("Capture source:", self.source_combo)
        self.method_combo = QComboBox()
        self.method_combo.addItem("Automatic (upgrade to WGC when covered)", 0)
        self.method_combo.addItem("Legacy BitBlt (visible desktop only)", 1)
        self.method_combo.addItem("Modern WGC (recommended)", 2)
        cap_form.addRow("Window method:", self.method_combo)
        self.covered_mode = QCheckBox(
            "Protect the target when another window covers it (Modern WGC)")
        cap_form.addRow(self.covered_mode)
        method_hint = QLabel(
            "Window Capture + Modern WGC reads the restored target surface even "
            "when another app covers it. Minimized windows cannot be captured; "
            "Chromium apps may also need anti-occlusion launch flags. When this "
            "protection is enabled, GhostRec uses WGC even if Automatic or "
            "BitBlt is selected.")
        method_hint.setObjectName("muted")
        method_hint.setWordWrap(True)
        cap_form.addRow("", method_hint)
        self.auto_detect = QCheckBox(
            "Detect apps that throttle their own rendering when covered")
        cap_form.addRow(self.auto_detect)
        auto_hint = QLabel(
            "GhostRec checks Chromium/Electron processes and offers a safe "
            "launcher when the app itself pauses rendering. This is separate "
            "from WGC, which handles the covered window surface.")
        auto_hint.setObjectName("muted")
        auto_hint.setWordWrap(True)
        cap_form.addRow("", auto_hint)
        wv_row = QHBoxLayout()
        self.webview_label = QLabel("")
        self.webview_label.setObjectName("muted")
        self.webview_label.setWordWrap(True)
        self.webview_btn = QPushButton("Remove")
        self.webview_btn.clicked.connect(self._clear_webview2)
        wv_row.addWidget(self.webview_label, 1)
        wv_row.addWidget(self.webview_btn)
        cap_form.addRow("Teams / WebView2:", wv_row)
        root.addWidget(cap_box)

        # -- Output ----------------------------------------------------------
        out_box = QGroupBox("Output")
        out_form = _form(out_box)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        self.folder_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(browse)
        out_form.addRow("Save folder:", folder_row)
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 60)
        self.poll_spin.setSuffix(" s")
        out_form.addRow("Status check interval:", self.poll_spin)
        root.addWidget(out_box)

        # -- Audio -----------------------------------------------------------
        audio_box = QGroupBox("Audio monitoring")
        audio_form = _form(audio_box)
        self.audio_check = QCheckBox("Warn when the sound goes silent")
        audio_form.addRow(self.audio_check)
        self.input_edit = QLineEdit()
        audio_form.addRow("OBS input name:", self.input_edit)
        self.silence_db = QDoubleSpinBox()
        self.silence_db.setRange(-100.0, 0.0)
        self.silence_db.setSingleStep(0.5)
        self.silence_db.setDecimals(1)
        self.silence_db.setSuffix(" dB")
        audio_form.addRow("Silence threshold:", self.silence_db)
        self.silence_secs = QSpinBox()
        self.silence_secs.setRange(1, 600)
        self.silence_secs.setSuffix(" s")
        audio_form.addRow("Warn after silence of:", self.silence_secs)
        self.minimize_secs = QSpinBox()
        self.minimize_secs.setRange(1, 3600)
        self.minimize_secs.setSuffix(" s")
        audio_form.addRow("Warn after minimized for:", self.minimize_secs)
        root.addWidget(audio_box)

        root.addStretch(1)

        # -- Save (pinned under the scroll area) --------------------------------
        save_row = QHBoxLayout()
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("muted")
        save_row.addStretch(1)
        save_row.addWidget(self.saved_label)
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("primary")
        save_row.addWidget(self.save_btn)
        outer.addLayout(save_row)

        self.test_btn.clicked.connect(self._emit_test)
        self.launch_btn.clicked.connect(
            lambda: self.launch_obs_requested.emit(self.port_spin.value()))
        self.save_btn.clicked.connect(self._emit_save)

    # -- API used by the main window ----------------------------------------- #

    def load_from(self, cfg):
        self._loading = True
        self._cfg = copy.deepcopy(cfg)
        obs = cfg.get("obs", {})
        audio = cfg.get("audio", {})
        self.host_edit.setText(obs.get("host", "127.0.0.1"))
        self.port_spin.setValue(int(obs.get("port", 4455)))
        self.pwd_edit.setText(obs.get("password", ""))
        self.scene_edit.setText(cfg.get("capture_scene_name", "ClassRecScene"))
        self.source_edit.setText(cfg.get("capture_source_name", "ClassCapture"))
        capture = cfg.get("capture", {})
        idx = self.source_combo.findData(capture.get("source", "window"))
        self.source_combo.setCurrentIndex(max(0, idx))
        idx = self.method_combo.findData(int(capture.get("method", 2)))
        self.method_combo.setCurrentIndex(max(0, idx))
        self.auto_detect.setChecked(bool(capture.get("auto", True)))
        self.covered_mode.setChecked(bool(capture.get("covered", True)))
        self.folder_edit.setText(cfg.get("output_folder", "./recordings"))
        self.poll_spin.setValue(int(cfg.get("poll_seconds", 3)))
        self.audio_check.setChecked(bool(audio.get("check", True)))
        self.input_edit.setText(audio.get("input_name", "Desktop Audio"))
        self.silence_db.setValue(float(audio.get("silence_db", -55.0)))
        self.silence_secs.setValue(int(audio.get("silence_alert_seconds", 30)))
        self.minimize_secs.setValue(int(audio.get("minimize_warn_seconds", 60)))
        ui = cfg.get("ui", {})
        idx = self.appearance_combo.findData(ui.get("appearance", "auto"))
        self.appearance_combo.setCurrentIndex(max(0, idx))
        self.native_frame.setChecked(bool(ui.get("native_frame", False)))
        self.refresh_webview2_state()
        self._loading = False

    def collect(self):
        """Read the form into a full config dict (unknown keys preserved)."""
        cfg = copy.deepcopy(self._cfg)
        cfg.setdefault("obs", {})
        cfg["obs"]["host"] = self.host_edit.text().strip() or "127.0.0.1"
        cfg["obs"]["port"] = int(self.port_spin.value())
        cfg["obs"]["password"] = self.pwd_edit.text()
        cfg["capture_scene_name"] = (self.scene_edit.text().strip()
                                     or "ClassRecScene")
        cfg["capture_source_name"] = (self.source_edit.text().strip()
                                      or "ClassCapture")
        cfg["output_folder"] = self.folder_edit.text().strip() or "./recordings"
        capture = cfg.setdefault("capture", {})
        capture["source"] = self.source_combo.currentData()
        capture["method"] = int(self.method_combo.currentData())
        capture["covered"] = bool(self.covered_mode.isChecked())
        capture["auto"] = bool(self.auto_detect.isChecked())
        cfg["poll_seconds"] = int(self.poll_spin.value())
        audio = cfg.setdefault("audio", {})
        audio["check"] = bool(self.audio_check.isChecked())
        audio["input_name"] = self.input_edit.text().strip() or "Desktop Audio"
        audio["silence_db"] = float(self.silence_db.value())
        audio["silence_alert_seconds"] = int(self.silence_secs.value())
        audio["minimize_warn_seconds"] = int(self.minimize_secs.value())
        ui = cfg.setdefault("ui", {})
        ui["appearance"] = self.appearance_combo.currentData() or "auto"
        ui["native_frame"] = bool(self.native_frame.isChecked())
        return cfg

    def show_test_result(self, ok, msg):
        color = theme.OK if ok else theme.ERR
        self.test_label.setStyleSheet(f"color: {color};")
        self.test_label.setText(f"{'✔' if ok else '✖'} {msg}")

    def show_launch_result(self, ok, msg):
        color = theme.OK if ok else theme.ERR
        self.test_label.setStyleSheet(f"color: {color};")
        self.test_label.setText(f"{'✔' if ok else '✖'} {msg}")

    def show_saved(self):
        self.saved_label.setText("Saved.")

    # -- internals ------------------------------------------------------------ #

    def refresh_webview2_state(self):
        from ghostrec.core.safe_apps import webview2_setting_active
        active = webview2_setting_active()
        self.webview_label.setText(
            "Recording-safe setting is ON for WebView2 apps (new Teams). "
            "Restart those apps after removing it." if active else
            "Off. Turned on by “Make recording-safe” for new Teams.")
        self.webview_btn.setEnabled(active)

    def _clear_webview2(self):
        from ghostrec.core.safe_apps import clear_webview2_setting
        try:
            clear_webview2_setting()
        except OSError as e:
            self.webview_label.setText(f"Could not remove it: {e}")
            return
        self.refresh_webview2_state()

    def _emit_appearance(self, *_):
        if not self._loading:
            # live preview; persisted with "Save Settings"
            self.appearance_changed.emit(
                self.appearance_combo.currentData() or "auto")

    def _toggle_pwd(self, show):
        self.pwd_edit.setEchoMode(QLineEdit.EchoMode.Normal if show
                                  else QLineEdit.EchoMode.Password)

    def _browse_folder(self):
        start = self.folder_edit.text() or "."
        chosen = QFileDialog.getExistingDirectory(self, "Choose save folder",
                                                  start)
        if chosen:
            self.folder_edit.setText(chosen)

    def _emit_test(self):
        self.test_label.setStyleSheet("")
        self.test_label.setText("Testing…")
        self.test_requested.emit(self.host_edit.text().strip() or "127.0.0.1",
                                 int(self.port_spin.value()),
                                 self.pwd_edit.text())

    def _emit_save(self):
        self.saved_label.setText("")
        self.save_requested.emit(self.collect())
