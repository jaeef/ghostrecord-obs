"""Offscreen UI checks for behaviour that broke before (no real windows)."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from ghostrec.ui import dialogs, theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    qapp = QApplication.instance() or QApplication([])
    theme.apply(qapp, "dark")
    return qapp


def _press_later(key, attempts=40):
    """Send a key to the open alert. Offscreen Qt has no 'active' window, so
    find the MacAlert among top-level widgets; retry until it is shown, and
    close it as a fallback so a failing test can never hang the suite."""
    def press(left=attempts):
        dlg = next((w for w in QApplication.topLevelWidgets()
                    if isinstance(w, dialogs.MacAlert) and w.isVisible()),
                   None)
        if dlg is None:
            if left:
                QTimer.singleShot(50, lambda: press(left - 1))
            return
        QApplication.sendEvent(dlg, QKeyEvent(
            QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        if dlg.isVisible():
            QTimer.singleShot(500, dlg.reject)
    QTimer.singleShot(100, press)


def test_alert_enter_and_escape(app):
    host = QWidget()
    _press_later(Qt.Key.Key_Return)
    assert dialogs.confirm(host, "Restart?", ok="Restart") is True
    _press_later(Qt.Key.Key_Escape)
    assert dialogs.confirm(host, "Restart?", ok="Restart") is False


def test_enter_never_triggers_destructive_action(app):
    _press_later(Qt.Key.Key_Return)
    assert dialogs.confirm(QWidget(), "Delete?", ok="Move to Recycle Bin",
                           destructive=True) is False


def test_activity_log_filters_and_counts(app):
    from ghostrec.ui.widgets import ActivityLog
    log = ActivityLog()
    log.add("rec", "Recording started", "10:00:00")
    log.add("audio", "⚠ WARNING: no sound", "10:00:05")
    log.add("error", "OBS failed", "10:00:09")

    def visible():
        return sum(not log.list.item(i).isHidden()
                   for i in range(log.list.count()))

    log._on_filter(log._seg_buttons["warn"])
    assert visible() == 2
    log._on_filter(log._seg_buttons["error"])
    assert visible() == 1
    log.clear()
    assert log.count() == 0


def test_library_buttons_follow_selection(app, tmp_path):
    from ghostrec.ui.pages.library import LibraryPage
    for i in range(2):
        (tmp_path / f"talk_2026-01-0{i + 1}_10-00-00.mkv").write_bytes(b"x")
    page = LibraryPage()
    page.set_folder(str(tmp_path))
    assert not page.delete_btn.isEnabled()
    page.table.selectRow(0)
    assert page.delete_btn.isEnabled() and page.open_btn.isEnabled()
    page.table.clearSelection()
    assert not page.delete_btn.isEnabled()
