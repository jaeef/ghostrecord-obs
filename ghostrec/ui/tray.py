"""System tray icon: recording state, quick actions, notifications."""

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ghostrec.ui import branding


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window, on_stop, on_quit):
        super().__init__(window)
        self._window = window
        self._recording = False

        menu = QMenu()
        show_action = QAction("Show GhostRec", menu)
        show_action.triggered.connect(self._show_window)
        self.stop_action = QAction("Stop recording", menu)
        self.stop_action.setEnabled(False)
        self.stop_action.triggered.connect(on_stop)
        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(on_quit)
        menu.addAction(show_action)
        menu.addAction(self.stop_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        self.setIcon(branding.status_icon(None))
        self.setToolTip("GhostRec OBS — idle")
        self.show()

    def set_recording(self, recording):
        self._recording = bool(recording)
        self.stop_action.setEnabled(self._recording)
        if not self._recording:
            self.setToolTip("GhostRec OBS — idle")

    def update_elapsed(self, elapsed):
        if self._recording:
            sec = int(elapsed)
            self.setToolTip("GhostRec — REC "
                            f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:"
                            f"{sec % 60:02d}")

    def notify(self, title, message, warn=False):
        icon = (QSystemTrayIcon.MessageIcon.Warning if warn
                else QSystemTrayIcon.MessageIcon.Information)
        self.showMessage(title, message, icon, 4000)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self):
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()
