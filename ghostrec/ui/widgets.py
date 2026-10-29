"""Small reusable widgets for the GhostRec GUI (Obsidian Studio)."""

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ghostrec.ui import theme


class StatusPill(QWidget):
    """Capsule pill with colored dot + short text (connection, recording, window state)."""

    COLORS = {
        "ok": theme.OK,
        "rec": theme.ERR,
        "warn": theme.WARN,
        "err": theme.ERR,
        "idle": theme.IDLE,
    }

    BG_COLORS = {
        "ok": theme.OK_BG,
        "rec": theme.REC_BG,
        "warn": theme.WARN_BG,
        "err": theme.REC_BG,
        "idle": theme.IDLE_BG,
    }

    BORDER_COLORS = {
        "ok": theme.OK_BORDER,
        "rec": theme.REC_BORDER,
        "warn": theme.WARN_BORDER,
        "err": theme.REC_BORDER,
        "idle": theme.IDLE_BORDER,
    }

    def __init__(self, text="", state="idle", parent=None):
        super().__init__(parent)
        self.setObjectName("statusPill")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 12, 4)
        lay.setSpacing(6)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(12)
        self._text = QLabel(text)
        self._text.setStyleSheet("font-weight: 600; font-size: 11px;")
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        self.set_state(state, text)

    def set_state(self, state, text=None):
        dot_color = self.COLORS.get(state, theme.IDLE)
        bg = self.BG_COLORS.get(state, "#161924")
        border = self.BORDER_COLORS.get(state, "#24283b")
        self._dot.setStyleSheet(f"color: {dot_color}; font-size: 10px;")
        self.setStyleSheet(f"""
            QWidget#statusPill {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """)
        if text is not None:
            self._text.setText(text)


class WindowCardWidget(QWidget):
    """Rich interactive card for displaying an open window (56px row)."""

    def __init__(self, win, icon=None, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("windowCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(12)

        # Native shell icon, 32x32
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(32, 32)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon is not None and not icon.isNull():
            pm = icon.pixmap(32, 32)
            self.icon_lbl.setPixmap(pm.scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.icon_lbl.setText("🪟")
            self.icon_lbl.setStyleSheet("font-size: 20px;")
        lay.addWidget(self.icon_lbl)

        # Title + tags
        info_lay = QVBoxLayout()
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(4)

        self.title_lbl = ElidedLabel(win.get("title", "Untitled"))
        self.title_lbl.setStyleSheet(
            "font-weight: 600; font-size: 13px; color: #ffffff;")
        info_lay.addWidget(self.title_lbl)

        tags_lay = QHBoxLayout()
        tags_lay.setContentsMargins(0, 0, 0, 0)
        tags_lay.setSpacing(6)

        exe_badge = QLabel(win.get("exe") or "unknown")
        exe_badge.setObjectName("tagProcess")
        tags_lay.addWidget(exe_badge)

        hwnd_val = win.get("hwnd", 0)
        hwnd_badge = QLabel(f"HWND 0x{hwnd_val:08X}")
        hwnd_badge.setObjectName("tagHwnd")
        tags_lay.addWidget(hwnd_badge)

        cls_val = win.get("cls", "")
        if cls_val:
            cls_lbl = ElidedLabel(cls_val)
            cls_lbl.setObjectName("tagClass")
            cls_lbl.setMaximumWidth(240)
            tags_lay.addWidget(cls_lbl)

        tags_lay.addStretch(1)
        info_lay.addLayout(tags_lay)
        lay.addLayout(info_lay, 1)

        # Right CTA hint
        cta = QLabel("Select ➔")
        cta.setStyleSheet(
            f"color: {theme.ACCENT}; font-size: 12px; font-weight: 700;")
        lay.addWidget(cta)



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
                color = QColor("#1a1d2b")
            p.setBrush(color)
            p.drawRoundedRect(rect, 2.5, 2.5)

        p.setPen(QColor(theme.TEXT if self._enabled else theme.IDLE))
        p.drawText(QRect(bar.right() + 6, full.top(), text_w, full.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   text)
