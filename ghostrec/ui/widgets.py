"""Small reusable widgets for the GhostRec GUI."""

from PyQt6.QtCore import QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QPushButton,
                             QSizePolicy, QVBoxLayout, QWidget)

from ghostrec.ui import theme


class Segmented(QWidget):
    """Windows-style segmented filter. Buttons never shrink below their
    label (they used to be squeezed into "Al / w / p")."""

    changed = pyqtSignal(str)

    def __init__(self, options, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        group = QButtonGroup(self)
        self.buttons = {}
        for i, (key, label) in enumerate(options):
            b = QPushButton(label)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            group.addButton(b)
            lay.addWidget(b)
            self.buttons[key] = b


class StatusPill(QWidget):
    """Capsule pill with colored dot + short text (connection, recording, window state)."""

    # state -> (dot color, tinted bg, border) — read lazily so the pill follows
    # runtime light/dark switches (see restyle()).
    @staticmethod
    def _colors(state):
        return {
            "ok": (theme.OK, theme.OK_BG, theme.OK_BORDER),
            "rec": (theme.ERR, theme.REC_BG, theme.REC_BORDER),
            "warn": (theme.WARN, theme.WARN_BG, theme.WARN_BORDER),
            "err": (theme.ERR, theme.REC_BG, theme.REC_BORDER),
        }.get(state, (theme.IDLE, theme.IDLE_BG, theme.IDLE_BORDER))

    def __init__(self, text="", state="idle", parent=None):
        super().__init__(parent)
        self.setObjectName("statusPill")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 0, 11, 0)
        lay.setSpacing(6)
        self._dot = QLabel()
        self._dot.setFixedSize(6, 6)
        self._text = QLabel(text)
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        self._state = state
        self.set_state(state, text)

    def set_state(self, state, text=None):
        self._state = state
        dot_color, bg, border = self._colors(state)
        self._dot.setStyleSheet(
            f"background: {dot_color}; border-radius: 3px;")
        self._text.setStyleSheet(
            f"color: {theme.TEXT}; font-weight: 500; font-size: 11px; "
            "background: transparent;")
        self.setStyleSheet(f"""
            QWidget#statusPill {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 11px;
            }}
        """)
        if text is not None:
            self._text.setText(text)

    def restyle(self):
        self.set_state(self._state)


class ElidedLabel(QLabel):
    """QLabel that middle-elides long text but keeps the full tooltip."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        super().setText(text)
        self.setToolTip(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full)
        self._apply()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def _apply(self):
        fm = self.fontMetrics()
        elided = fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle,
                               max(0, self.width()))
        super().setText(elided)


class LevelMeter(QWidget):
    """Dotted/segmented audio level meter, -70..0 dB (OBS-style)."""

    SEGMENTS = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -100.0
        self._enabled = False
        self.setMinimumHeight(24)
        self.setMinimumWidth(220)

    def set_db(self, db):
        self._db = float(db)
        self.update()

    def set_enabled(self, on):
        self._enabled = bool(on)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        text = f"{self._db:5.1f} dB" if self._enabled else "audio check off"
        text_w = p.fontMetrics().horizontalAdvance(text) + 10
        full = self.rect()

        bar = QRect(full.left() + 2, full.top() + 5,
                    max(20, full.width() - text_w - 6), full.height() - 10)
        n = self.SEGMENTS
        gap = 3
        seg_w = (bar.width() - gap * (n - 1)) / n
        level = max(0.0, min(1.0, (self._db + 70.0) / 70.0)) if self._enabled else 0.0

        for i in range(n):
            pos = (i + 1) / n                 # this segment's dB position
            x = bar.left() + i * (seg_w + gap)
            rect = QRectF(x, bar.top(), seg_w, bar.height())
            if self._enabled and pos <= level + 1e-9:
                db_at = -70.0 + 70.0 * pos
                if db_at <= -20:
                    color = QColor(theme.OK)
                elif db_at <= -6:
                    color = QColor(theme.WARN)
                else:
                    color = QColor(theme.ERR)
            else:
                color = QColor(theme.FILL)
            p.setBrush(color)
            p.drawRoundedRect(rect, 2.5, 2.5)

        p.setPen(QColor(theme.TEXT if self._enabled else theme.IDLE))
        p.drawText(QRect(bar.right() + 6, full.top(), text_w, full.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   text)


class ActivityLog(QWidget):
    """Structured event log: severity icon, time, source tag, message.

    Filter segments (All / Warnings / Errors) with live counts, Copy to
    clipboard and Clear. Auto-scrolls only when already at the bottom.
    """

    MAX = 300
    _SOURCES = {"rec": "Recording", "pin": "Window", "obs": "OBS",
                "audio": "Audio", "file": "File", "apps": "Apps",
                "settings": "Settings", "warn": "Warning", "error": "Error"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []          # (level, stamp, source, text)
        self._filter = "all"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Activity")
        title.setObjectName("sectionHeader")
        head.addWidget(title)
        head.addSpacing(6)
        seg = Segmented([("all", "All"), ("warn", "Warnings"),
                         ("error", "Errors")])
        self._seg_buttons = seg.buttons
        seg.changed.connect(self._on_filter)
        head.addWidget(seg)
        head.addStretch(1)
        from ghostrec.ui.chrome import GLYPHS
        self.copy_btn = QPushButton(GLYPHS["copy"])
        self.copy_btn.setObjectName("iconButton")
        self.copy_btn.setFixedSize(30, 28)
        self.copy_btn.setToolTip("Copy the log to the clipboard")
        self.copy_btn.setAccessibleName("Copy log")
        self.copy_btn.clicked.connect(self.copy)
        self.clear_btn = QPushButton(GLYPHS["delete"])
        self.clear_btn.setObjectName("iconButton")
        self.clear_btn.setFixedSize(30, 28)
        self.clear_btn.setToolTip("Clear the log")
        self.clear_btn.setAccessibleName("Clear log")
        self.clear_btn.clicked.connect(self.clear)
        head.addWidget(self.copy_btn)
        head.addWidget(self.clear_btn)
        lay.addLayout(head)

        self.list = QListWidget()
        self.list.setObjectName("activityFeed")
        self.list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        lay.addWidget(self.list, 1)
        self.empty = QLabel("Events appear here while you record.")
        self.empty.setObjectName("emptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty, 1)
        self.list.hide()
        self._update_counts()

    @staticmethod
    def level_for(source, text):
        up = text.upper()
        if (source == "error" or "ERROR" in up or "FAILED" in up
                or "ABORT" in up):
            return "error"
        if "⚠" in text or "WARNING" in up or source == "warn":
            return "warn"
        if "✔" in text or "SAVED" in up or "RESTORED" in up:
            return "ok"
        return "info"

    def add(self, source, text, stamp):
        level = self.level_for(source, text)
        text = text.replace("⚠", "").replace("✔", "").strip()
        self._entries.append((level, stamp, source, text))
        bar = self.list.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, level)
        row = self._row(level, stamp, source, text)
        item.setSizeHint(QSize(0, 26))
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        item.setHidden(not self._matches(level))
        while self.list.count() > self.MAX:
            self.list.takeItem(0)
            self._entries.pop(0)
        self.list.show()
        self.empty.hide()
        self._update_counts()
        if at_bottom:
            self.list.scrollToBottom()

    def _row(self, level, stamp, source, text):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)
        color = {"error": theme.ERR, "warn": theme.WARN, "ok": theme.OK
                 }.get(level, theme.DIMMED)
        from ghostrec.ui.chrome import GLYPHS
        glyph = {"error": GLYPHS["error"], "warn": GLYPHS["warning"],
                 "ok": GLYPHS["check"]}.get(level, "•")
        dot = QLabel(glyph)
        dot.setFixedSize(16, 16)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if level == "info":
            dot.setStyleSheet(f"color: {color}; font-size: 14px; "
                              "background: transparent;")
        else:
            dot.setStyleSheet(f"color: {color}; font-size: 13px; "
                              f"font-family: {theme.FONT_ICONS}; "
                              "background: transparent;")
        t = QLabel(stamp)
        t.setObjectName("logTime")
        tag = QLabel(self._SOURCES.get(source, source.title()))
        tag.setObjectName("logTag")
        tag.setFixedWidth(68)
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = ElidedLabel(text)
        msg.setObjectName({"error": "logError", "warn": "logWarn"
                           }.get(level, "logText"))
        lay.addWidget(dot)
        lay.addWidget(t)
        lay.addWidget(tag)
        lay.addWidget(msg, 1)
        return w

    def _matches(self, level):
        return (self._filter == "all" or level == self._filter
                or (self._filter == "warn" and level == "error"))

    def _on_filter(self, key):
        self._filter = key
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(not self._matches(
                item.data(Qt.ItemDataRole.UserRole)))
        self.list.scrollToBottom()

    def _update_counts(self):
        warns = sum(1 for e in self._entries if e[0] in ("warn", "error"))
        errs = sum(1 for e in self._entries if e[0] == "error")
        self._seg_buttons["all"].setText(f"All  {len(self._entries)}")
        self._seg_buttons["warn"].setText(f"Warnings  {warns}")
        self._seg_buttons["error"].setText(f"Errors  {errs}")

    def copy(self):
        lines = [f"{s}  [{src}] {t}" for _, s, src, t in self._entries]
        QApplication.clipboard().setText("\n".join(lines))
        from ghostrec.ui.chrome import GLYPHS
        self.copy_btn.setText(GLYPHS["check"])
        QTimer.singleShot(1500, lambda: self.copy_btn.setText(GLYPHS["copy"]))

    def clear(self):
        self._entries.clear()
        self.list.clear()
        self.list.hide()
        self.empty.show()
        self._update_counts()

    def count(self):
        return len(self._entries)
