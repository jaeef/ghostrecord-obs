"""Settings page: OBS connection, output folder, audio thresholds."""

import copy

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QDoubleSpinBox, QFileDialog,
                             QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QSpinBox,
                             QVBoxLayout, QWidget)


class SettingsPage(QWidget):
    test_requested = pyqtSignal(str, int, str)  # host, port, password
    launch_obs_requested = pyqtSignal(int)      # port
    save_requested = pyqtSignal(dict)           # full config dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = {}
        self._loading = False

        root = QVBoxLayout(self)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        # -- OBS -------------------------------------------------------------
        obs_box = QGroupBox("OBS WebSocket")
        form = QFormLayout(obs_box)
        self.host_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        password_row = QHBoxLayout()
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
        self.test_btn = QPushButton("Test connection")
        self.launch_btn = QPushButton("Start OBS…")
        buttons.addWidget(self.test_btn)
        buttons.addWidget(self.launch_btn)
        buttons.addStretch(1)
        form.addRow("", buttons)

        self.test_label = QLabel("")
        self.test_label.setObjectName("muted")
        self.test_label.setWordWrap(True)
        form.addRow("", self.test_label)
        root.addWidget(obs_box)

        # -- Output ----------------------------------------------------------
        out_box = QGroupBox("Output")
        out_form = QFormLayout(out_box)
        folder_row = QHBoxLayout()
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
        audio_form = QFormLayout(audio_box)
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

        # -- Save ------------------------------------------------------------
        save_row = QHBoxLayout()
        self.save_btn = QPushButton("Save settings")
        self.save_btn.setObjectName("primary")
        save_row.addWidget(self.save_btn)
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("muted")
        save_row.addWidget(self.saved_label)
        save_row.addStretch(1)
        root.addLayout(save_row)
        root.addStretch(1)

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
        self.folder_edit.setText(cfg.get("output_folder", "./recordings"))
        self.poll_spin.setValue(int(cfg.get("poll_seconds", 3)))
        self.audio_check.setChecked(bool(audio.get("check", True)))
        self.input_edit.setText(audio.get("input_name", "Desktop Audio"))
        self.silence_db.setValue(float(audio.get("silence_db", -55.0)))
        self.silence_secs.setValue(int(audio.get("silence_alert_seconds", 30)))
        self.minimize_secs.setValue(int(audio.get("minimize_warn_seconds", 60)))
        self._loading = False

    def collect(self):
        """Read the form into a full config dict (unknown keys preserved)."""
        cfg = copy.deepcopy(self._cfg)
        cfg.setdefault("obs", {})
        cfg["obs"]["host"] = self.host_edit.text().strip() or "127.0.0.1"
        cfg["obs"]["port"] = int(self.port_spin.value())
        cfg["obs"]["password"] = self.pwd_edit.text()
        cfg["output_folder"] = self.folder_edit.text().strip() or "./recordings"
        cfg["poll_seconds"] = int(self.poll_spin.value())
        audio = cfg.setdefault("audio", {})
        audio["check"] = bool(self.audio_check.isChecked())
        audio["input_name"] = self.input_edit.text().strip() or "Desktop Audio"
        audio["silence_db"] = float(self.silence_db.value())
        audio["silence_alert_seconds"] = int(self.silence_secs.value())
        audio["minimize_warn_seconds"] = int(self.minimize_secs.value())
        return cfg

    def show_test_result(self, ok, msg):
        color = "#3fb950" if ok else "#f85149"
        self.test_label.setStyleSheet(f"color: {color};")
        self.test_label.setText(f"{'✔' if ok else '✖'} {msg}")

    def show_launch_result(self, ok, msg):
        color = "#3fb950" if ok else "#f85149"
        self.test_label.setStyleSheet(f"color: {color};")
        self.test_label.setText(f"{'✔' if ok else '✖'} {msg}")

    def show_saved(self):
        self.saved_label.setText("Saved.")

    # -- internals ------------------------------------------------------------ #

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
