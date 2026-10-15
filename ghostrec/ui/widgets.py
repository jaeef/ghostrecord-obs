"""Small reusable widgets for the GhostRec GUI."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ghostrec.ui import theme


class StatusPill(QWidget):
    """Colored dot + short text (connection, recording, window state)."""

    COLORS = {
        "ok": theme.OK,
        "rec": theme.ERR,
        "warn": theme.WARN,
        "err": theme.ERR,
        "idle": theme.IDLE,
    }

    def __init__(self, text="", state="idle", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._text = QLabel(text)
        lay.addWidget(self._dot)
        lay.addWidget(self._text)
        self.set_state(state, text)

    def set_state(self, state, text=None):
        self._dot.setStyleSheet(f"color: {self.COLORS.get(state, theme.IDLE)};")
        if text is not None:
            self._text.setText(text)


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
    """Horizontal audio level meter, -70..0 dB."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = -100.0
        self._enabled = False
        self.setMinimumHeight(20)
        self.setMinimumWidth(200)

    def set_db(self, db):
        self._db = float(db)
        self.update()

    def set_enabled(self, on):
        self._enabled = bool(on)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 2, 0, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#23252b"))
        p.drawRoundedRect(r, 6, 6)
        if self._enabled:
            frac = max(0.0, min(1.0, (self._db + 70.0) / 70.0))
            if frac > 0.0:
                w = int(r.width() * frac)
                bar = r.adjusted(0, 0, -(r.width() - w), 0)
                if self._db <= -20:
                    color = theme.OK
                elif self._db <= -6:
                    color = theme.WARN
                else:
                    color = theme.ERR
                p.setBrush(QColor(color))
                p.drawRoundedRect(bar, 6, 6)
            text = f"{self._db:5.1f} dB"
            p.setPen(QColor(theme.TEXT))
        else:
            text = "audio check off"
            p.setPen(QColor(theme.IDLE))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
