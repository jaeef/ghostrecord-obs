"""QApplication bootstrap: macOS-style theme, single-instance guard, main window."""

import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from ghostrec.ui import branding, theme
from ghostrec.ui.main_window import MainWindow

_SINGLE_KEY = "ghostrec-obs-single-instance"


def main():
    QCoreApplication.setApplicationName("GhostRec OBS")
    QCoreApplication.setOrganizationName("GhostRec")

    app = QApplication(sys.argv)
    app.setApplicationDisplayName("GhostRec OBS")
    app.setWindowIcon(branding.app_icon())
    theme.apply(app, _saved_appearance())

    if _forward_to_existing_instance():
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(_SINGLE_KEY)
    server.listen(_SINGLE_KEY)

    try:
        window = MainWindow()
    except (OSError, ValueError) as e:
        from ghostrec.ui import dialogs
        dialogs.error(None, "GhostRec could not start",
                      "config.json has an error. Fix it, or delete it to "
                      "start with defaults.", detail=str(e))
        return 1

    def _on_new_connection():
        while server.hasPendingConnections():
            conn = server.nextPendingConnection()
            conn.readAll()
            window.showNormal()
            window.raise_()
            window.activateWindow()

    server.newConnection.connect(_on_new_connection)
    window.show()
    return app.exec()


def _saved_appearance():
    """Appearance preference from config.json, before the window exists."""
    try:
        from ghostrec.core import config as gcfg
        return gcfg.load_config().get("ui", {}).get("appearance", "auto")
    except Exception:
        return "auto"


def _forward_to_existing_instance():
    """If another GhostRec is already running, bring it to front and exit."""
    sock = QLocalSocket()
    sock.connectToServer(_SINGLE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False
