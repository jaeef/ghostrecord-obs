"""System tray icon: recording state, quick actions, notifications."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from ghostrec.ui import theme


def _dot_icon(color):
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(pm.rect().adjusted(10, 10, -10, -10))
    if color == theme.ERR:  # recording: inner white dot
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(pm.rect().adjusted(24, 24, -24, -24))
    p.end()
    return QIcon(pm)


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window, on_stop, on_quit):
        super().__init__(window)
        self._window = window
        self._icon_idle = _dot_icon(theme.IDLE)
        self._icon_rec = _dot_icon(theme.ERR)
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

        self.setIcon(self._icon_idle)
        self.setToolTip("GhostRec OBS — idle")
        self.show()

    def set_recording(self, recording):
        self._recording = bool(recording)
        self.stop_action.setEnabled(self._recording)
        self.setIcon(self._icon_rec if self._recording else self._icon_idle)
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
