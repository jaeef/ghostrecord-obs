"""Window picker page: rich window card list + recording name + Start (No search)."""

from PyQt6.QtCore import QFileInfo, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QCheckBox, QFileIconProvider, QHBoxLayout,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QVBoxLayout, QWidget)

from ghostrec.core.library import unique_recording_name
from ghostrec.core.recorder import sanitize_recording_name
from ghostrec.core.windows import list_windows
from ghostrec.ui.widgets import WindowCardWidget


class PickerPage(QWidget):
    """Lists open windows as Obsidian-style cards; emits record_requested(window_dict, name)."""

    record_requested = pyqtSignal(dict, str)
    chrome_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wins = []
        self._busy = False
        self._output_dir = ""
        self._icon_provider = QFileIconProvider()
        self._icons = {}  # exe_path -> QIcon

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Header Titles
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Select Target Window")
        title.setObjectName("pageTitle")
        title_box.addWidget(title)
        subtitle = QLabel("Locks onto this exact window by HWND — background activity and other apps are never captured.")
        subtitle.setObjectName("muted")
        title_box.addWidget(subtitle)
        lay.addLayout(title_box)

        # Top Bar (Window counter + Refresh controls, No Search)
        top = QHBoxLayout()
        self.count_label = QLabel("Scanning windows…")
        self.count_label.setStyleSheet("color: #9ca3af; font-size: 12px; font-weight: 500;")
        self.auto_refresh = QCheckBox("Auto-refresh")
        self.auto_refresh.setChecked(True)
        self.refresh_btn = QPushButton("↻ Refresh List")
        self.refresh_btn.setObjectName("accent")
        self.chrome_btn = QPushButton("🌐 Isolated recording Chrome")
        self.chrome_btn.setObjectName("accent")
        self.chrome_btn.setToolTip(
            "Opens a SEPARATE Chrome instance with anti-throttle flags, so it "
            "keeps rendering (and recording sharply) while other windows cover "
            "it. Uses its own profile — your normal Chrome stays untouched. "
            "Use the Live page button to restart your normal Chrome instead.")

        top.addWidget(self.count_label)
        top.addStretch(1)
        top.addWidget(self.auto_refresh)
        top.addWidget(self.chrome_btn)
        top.addWidget(self.refresh_btn)
        lay.addLayout(top)

        # Card List of Windows
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: #0f1118;
                border: 1px solid #1f2230;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget::item {
                background: #141722;
                border: 1px solid #202434;
                border-radius: 8px;
                margin-bottom: 2px;
            }
            QListWidget::item:hover {
                background: #1a1e2c;
                border-color: #3b4259;
            }
            QListWidget::item:selected {
                background: #231e3d;
                border: 1px solid #815bf5;
            }
        """)
        lay.addWidget(self.list_widget, 1)

        # Bottom Bar: Recording Name + Start CTA
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        name_lbl = QLabel("File name:")
        name_lbl.setStyleSheet("font-weight: 600; color: #9ca3af;")
        bottom.addWidget(name_lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("recording")
        self.name_edit.setText(QSettings().value("last_name", "") or "")
        bottom.addWidget(self.name_edit, 1)
        self.save_hint = QLabel("")
        self.save_hint.setObjectName("dimmed")
        bottom.addWidget(self.save_hint)

        self.start_btn = QPushButton("● Start Recording")
        self.start_btn.setObjectName("primary")
        self.start_btn.setMinimumHeight(38)
        bottom.addWidget(self.start_btn)
        lay.addLayout(bottom)

        # Signals
        self.name_edit.textChanged.connect(self._update_hint)
        self.refresh_btn.clicked.connect(self.refresh)
        self.chrome_btn.clicked.connect(self.chrome_requested.emit)
        self.start_btn.clicked.connect(self._start)
        self.list_widget.itemDoubleClicked.connect(lambda *_: self._start())
        # Enter starts the recording for the selected window
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            QShortcut(QKeySequence(key), self.list_widget,
                      context=Qt.ShortcutContext.WidgetWithChildrenShortcut
                      ).activated.connect(self._start)

        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._auto_tick)
        self._timer.start()

        self.refresh()

    # -- API used by the main window ---------------------------------------- #

    def set_output_dir(self, folder):
        """Where recordings land — used to auto-de-duplicate file names."""
        self._output_dir = folder or ""
        self._update_hint()

    def _resolved_name(self):
        """Base name typed by the user + automatic duplicate avoidance."""
        base = sanitize_recording_name(self.name_edit.text())
        return base, unique_recording_name(self._output_dir, base)

    def _update_hint(self, *_):
        base, final = self._resolved_name()
        if final != base:
            self.save_hint.setText(f"→ saves as {final}")
            self.save_hint.setStyleSheet(
                "color: #9675ff; font-size: 11px; font-weight: 600;")
        else:
            self.save_hint.setText("")
            self.save_hint.setStyleSheet("")

    def set_busy(self, busy):
        """Disable starting (a recording is in progress) and pause refresh."""
        self._busy = busy
        self.start_btn.setEnabled(not busy)
        self.start_btn.setText("● Start Recording" if not busy
                               else "● Recording in progress…")

    def refresh(self):
        prev_hwnd = None
        item = self.list_widget.currentItem()
        if item is not None:
            prev_data = item.data(Qt.ItemDataRole.UserRole)
            if prev_data:
                prev_hwnd = prev_data.get("hwnd")

        self._wins = list_windows()
        self.list_widget.clear()

        count = len(self._wins)
        self.count_label.setText(f"● {count} open windows available")

        for w in self._wins:
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(QSize(0, 50))
            item.setData(Qt.ItemDataRole.UserRole, w)

            icon = self._icon_for(w.get("exe_path", ""))
            card = WindowCardWidget(w, icon=icon)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, card)

            if prev_hwnd is not None and w["hwnd"] == prev_hwnd:
                self.list_widget.setCurrentItem(item)

        # If nothing selected, select the first window by default
        if self.list_widget.currentItem() is None and count > 0:
            self.list_widget.setCurrentRow(0)

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

    def _start(self):
        if self._busy:
            return
        item = self.list_widget.currentItem()
        if item is None:
            return
        win = item.data(Qt.ItemDataRole.UserRole)
        if not win:
            return
        # Auto-fill behaviour: the field keeps the base name you last used (or
        # typed); the duplicate-safe final name is previewed next to it.
        base, name = self._resolved_name()
        QSettings().setValue("last_name", base)
        self.record_requested.emit(win, name)
