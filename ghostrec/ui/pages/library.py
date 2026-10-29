"""Recordings library page: list, details, open, show in folder, delete."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView,
                             QLabel, QMessageBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from ghostrec.core.library import (delete_recording, human_size, open_file,
                                   scan_recordings, show_in_explorer)


def _hms(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


class LibraryPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder = ""
        self._rows = []
        self._durations = {}  # normcase(path) -> seconds (this app run only)

        lay = QVBoxLayout(self)
        title = QLabel("Recordings")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        self.folder_label = QLabel("")
        self.folder_label.setObjectName("muted")
        lay.addWidget(self.folder_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Recorded", "Size",
                                               "Format"])
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col,
                                        QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda *_: self._open())
        self.table.itemSelectionChanged.connect(self._update_details)
        lay.addWidget(self.table, 1)

        self.empty_label = QLabel("No recordings yet. Record a window and the "
                                  "finished file shows up here.")
        self.empty_label.setObjectName("muted")
        lay.addWidget(self.empty_label)

        self.details = QLabel("Select a recording to see its details.")
        self.details.setObjectName("details")
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(84)
        self.details.setAlignment(Qt.AlignmentFlag.AlignLeft
                                  | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.details)

        btns = QHBoxLayout()
        self.refresh_btn = QPushButton("↻ Refresh")
        self.refresh_btn.setObjectName("accent")
        self.open_btn = QPushButton("▶ Play")
        self.folder_btn = QPushButton("📂 Show in Explorer")
        self.delete_btn = QPushButton("🗑 Delete")
        btns.addWidget(self.refresh_btn)
        btns.addStretch(1)
        btns.addWidget(self.open_btn)
        btns.addWidget(self.folder_btn)
        btns.addWidget(self.delete_btn)
        lay.addLayout(btns)

        self.refresh_btn.clicked.connect(self.refresh)
        self.open_btn.clicked.connect(self._open)
        self.folder_btn.clicked.connect(self._show_folder)
        self.delete_btn.clicked.connect(self._delete)
        self._update_buttons()

    # -- API used by the main window ----------------------------------------- #

    def set_folder(self, folder):
        self._folder = folder or ""
        self.folder_label.setText(self._folder)
        self.refresh()

    def mark_recent(self, path, duration):
        """Remember a just-finished recording (duration in seconds), refresh
        the list and select it so its details are visible."""
        if duration:
            self._durations[os.path.normcase(path)] = duration
        self.refresh()
        self.select_path(path)

    def select_path(self, path):
        target = os.path.normcase(path or "")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            cur = item.data(Qt.ItemDataRole.UserRole) or ""
            if os.path.normcase(cur) == target:
                self.table.setCurrentCell(row, 0)
                return

    def refresh(self):
        prev = self._selected_path()
        self._rows = scan_recordings(self._folder)
        self.table.setRowCount(0)
        for rec in self._rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(f"{rec.name}{rec.ext}")
            name_item.setToolTip(rec.path)
            name_item.setData(Qt.ItemDataRole.UserRole, rec.path)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(rec.display_date))
            self.table.setItem(row, 2, QTableWidgetItem(human_size(rec.size_bytes)))
            self.table.setItem(row, 3, QTableWidgetItem(
                (rec.ext or "").lstrip(".").upper() or "—"))
        self.empty_label.setVisible(not self._rows)
        if prev:
            self.select_path(prev)
        self._update_details()
        self._update_buttons()

    # -- internals ------------------------------------------------------------ #

    def _selected_path(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return (item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def _update_details(self):
        path = self._selected_path()
        if not path:
            self.details.setText("Select a recording to see its details.")
            return
        rec = next((r for r in self._rows
                    if os.path.normcase(r.path) == os.path.normcase(path)), None)
        if rec is None:
            self.details.setText(path)
            return
        parts = [f"<b>{rec.name}{rec.ext}</b>",
                 f"Recorded: {rec.display_date}",
                 f"Size: {human_size(rec.size_bytes)}"]
        dur = self._durations.get(os.path.normcase(path))
        if dur:
            parts.append(f"Duration: {_hms(dur)}")
        parts.append(f"Path: {rec.path}")
        self.details.setText("<br>".join(parts))

    def _update_buttons(self):
        has = bool(self._selected_path())
        for b in (self.open_btn, self.folder_btn, self.delete_btn):
            b.setEnabled(has)

    def _open(self):
        path = self._selected_path()
        if path:
            open_file(path)

    def _show_folder(self):
        path = self._selected_path()
        if path:
            show_in_explorer(path)

    def _delete(self):
        path = self._selected_path()
        if not path:
            return
        answer = QMessageBox.question(
            self, "Delete recording",
            f"Delete this recording permanently?\n\n{os.path.basename(path)}")
        if answer == QMessageBox.StandardButton.Yes:
            try:
                delete_recording(path)
            except OSError as e:
                QMessageBox.warning(self, "Delete failed", str(e))
            self.refresh()
