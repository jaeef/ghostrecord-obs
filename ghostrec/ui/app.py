"""QApplication bootstrap: dark theme, single-instance guard, main window."""

import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox

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

    try:
        window = MainWindow()
    except (OSError, ValueError) as e:
        QMessageBox.critical(
            None, "GhostRec could not start",
            f"Configuration error:\n\n{e}\n\n"
            "Fix config.json or use Settings after recreating it.")
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
