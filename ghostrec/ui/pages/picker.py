"""Window picker page: searchable window list + recording name + Start."""

from PyQt6.QtCore import QFileInfo, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QCheckBox, QFileIconProvider, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ghostrec.core.recorder import sanitize_recording_name
from ghostrec.core.windows import list_windows


class PickerPage(QWidget):
    """Lists open windows; emits record_requested(window_dict, name)."""

    record_requested = pyqtSignal(dict, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wins = []
        self._busy = False
        self._icon_provider = QFileIconProvider()
        self._icons = {}  # exe_path -> QIcon

        lay = QVBoxLayout(self)

        title = QLabel("Pick a window to record")
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel("Only this exact window is recorded — other windows "
                          "are never captured.")
        subtitle.setObjectName("muted")
        lay.addWidget(subtitle)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search windows…")
        self.auto_refresh = QCheckBox("Auto-refresh")
        self.auto_refresh.setChecked(True)
        self.refresh_btn = QPushButton("↻ Refresh")
        top.addWidget(self.search, 1)
        top.addWidget(self.auto_refresh)
        top.addWidget(self.refresh_btn)
        lay.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["exe", "title"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setIconSize(self.tree.iconSize())
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setColumnWidth(0, 230)
        lay.addWidget(self.tree, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("recording")
        self.name_edit.setText(QSettings().value("last_name", "") or "")
        bottom.addWidget(self.name_edit, 1)
        self.start_btn = QPushButton("● Start recording")
        self.start_btn.setObjectName("primary")
        bottom.addWidget(self.start_btn)
        lay.addLayout(bottom)

        self.search.textChanged.connect(self._apply_filter)
        self.refresh_btn.clicked.connect(self.refresh)
        self.start_btn.clicked.connect(self._start)
        self.tree.itemDoubleClicked.connect(lambda *_: self._start())

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._auto_tick)
        self._timer.start()

        self.refresh()

    # -- API used by the main window ---------------------------------------- #

    def set_busy(self, busy):
        """Disable starting (a recording is in progress) and pause refresh."""
        self._busy = busy
        self.start_btn.setEnabled(not busy)
        self.start_btn.setText("● Start recording" if not busy
                               else "● Recording…")

    def refresh(self):
        prev_hwnd = None
        item = self.tree.currentItem()
        if item is not None:
            prev_hwnd = item.data(0, Qt.ItemDataRole.UserRole).get("hwnd")

        self._wins = list_windows()
        self.tree.clear()
        for w in self._wins:
            it = QTreeWidgetItem([w["exe"] or "?", w["title"]])
            it.setData(0, Qt.ItemDataRole.UserRole, w)
            it.setToolTip(1, f"{w['title']}\nhwnd {w['hwnd']}")
            icon = self._icon_for(w.get("exe_path", ""))
            if icon is not None:
                it.setIcon(0, icon)
            self.tree.addTopLevelItem(it)
            if prev_hwnd is not None and w["hwnd"] == prev_hwnd:
                self.tree.setCurrentItem(it)
        self._apply_filter(self.search.text())

    # -- internals ----------------------------------------------------------- #

    def _icon_for(self, exe_path):
        if not exe_path:
            return None
        if exe_path not in self._icons:
            self._icons[exe_path] = self._icon_provider.icon(QFileInfo(exe_path))
        return self._icons[exe_path]

    def _auto_tick(self):
        if self._busy or not self.auto_refresh.isChecked():
            return
        if not self.isVisible():
            return
        self.refresh()

    def _apply_filter(self, text):
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            w = it.data(0, Qt.ItemDataRole.UserRole)
            hay = f"{w.get('exe', '')}\n{w.get('title', '')}".lower()
            it.setHidden(bool(needle) and needle not in hay)

    def _start(self):
        if self._busy:
            return
        item = self.tree.currentItem()
        if item is None or item.isHidden():
            return
        win = item.data(0, Qt.ItemDataRole.UserRole)
        raw_name = self.name_edit.text()
        QSettings().setValue("last_name", raw_name)
        name = sanitize_recording_name(raw_name)
        self.record_requested.emit(win, name)
