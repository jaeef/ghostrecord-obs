"""QApplication bootstrap: dark theme, single-instance guard, main window."""

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
    theme.apply(app)

    if _forward_to_existing_instance():
        return 0

    server = QLocalServer()
    QLocalServer.removeServer(_SINGLE_KEY)
    server.listen(_SINGLE_KEY)

    window = MainWindow()

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
