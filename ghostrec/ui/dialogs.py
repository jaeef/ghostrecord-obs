"""Themed alerts that replace QMessageBox everywhere in the app.

Layout: app icon (with a caution badge for
warnings), bold centered title, secondary message, and buttons that sit side
by side when there are two or stack full-width when there are more. The parent
window is dimmed while the alert is open.

    choice = alert(parent, "Title", "Message",
                   buttons=[("Make recording-safe", "primary"),
                            ("Record anyway", "normal"),
                            ("Cancel", "cancel")],
                   kind="warning")
    -> the clicked label, or None when dismissed (Esc / Cancel role)
"""

from PyQt6.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF,
                          Qt)
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import (QApplication, QDialog, QGraphicsDropShadowEffect,
                             QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QVBoxLayout, QWidget)

from ghostrec.ui import branding, theme
from ghostrec.ui.chrome import GLYPHS

_BADGE = {"warning": ("warning", "WARN"), "error": ("error", "ERR"),
          "question": ("info", "ACCENT"), "info": None,
          "success": ("check", "OK")}


def _icon_pixmap(kind, size=64):
    """App icon with a small status badge in the corner."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.drawPixmap(QRectF(0, 0, size, size), branding.logo_pixmap(int(size * dpr)),
                 QRectF(0, 0, size * dpr, size * dpr))
    badge = _BADGE.get(kind)
    if badge:
        glyph, color_name = badge
        r = size * 0.22
        c = QPointF(size - r - 1, size - r - 1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.BG_ELEVATED))
        p.drawEllipse(c, r + 2.5, r + 2.5)
        p.setBrush(QColor(getattr(theme, color_name)))
        p.drawEllipse(c, r, r)
        f = QFont()
        f.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
        f.setPixelSize(int(r * 1.1))
        p.setFont(f)
        p.setPen(QColor(theme.ACCENT_TEXT if color_name == "ACCENT"
                        else "#1b1b1b" if color_name == "WARN" else "white"))
        p.drawText(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r),
                   Qt.AlignmentFlag.AlignCenter, GLYPHS[glyph])
    p.end()
    return pm


class _Dim(QWidget):
    """Translucent layer over the parent window while an alert is open."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90 if theme.is_dark() else 50))


class MacAlert(QDialog):
    WIDTH = 340
    SHADOW = 28

    def __init__(self, parent, title, message, buttons, kind="info",
                 detail=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog
                            | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setWindowTitle(title)
        self.result_label = None
        self._cancel_label = None

        outer = QVBoxLayout(self)
        m = self.SHADOW
        outer.setContentsMargins(m, m - 6, m, m + 6)

        card = QWidget()
        card.setObjectName("alertCard")
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setFixedWidth(self.WIDTH)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 150 if theme.is_dark() else 70))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(22, 22, 22, 18)
        lay.setSpacing(0)

        icon = QLabel()
        icon.setPixmap(_icon_pixmap(kind))
        icon.setFixedSize(64, 64)
        icon.setStyleSheet("background: transparent;")
        lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(14)

        t = QLabel(title)
        t.setObjectName("alertTitle")
        t.setWordWrap(True)
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(t)
        if message:
            lay.addSpacing(6)
            msg = QLabel(message)
            msg.setObjectName("alertText")
            msg.setWordWrap(True)
            msg.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            msg.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(msg)
        if detail:
            lay.addSpacing(10)
            d = QLabel(detail)
            d.setObjectName("alertDetail")
            d.setWordWrap(True)
            d.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            lay.addWidget(d)
        lay.addSpacing(18)

        stacked = len(buttons) > 2 or any(len(b[0]) > 16 for b in buttons)
        row = QVBoxLayout() if stacked else QHBoxLayout()
        row.setSpacing(8)
        ordered = list(buttons)
        # Windows order: action first (left / top), Cancel last
        ordered.sort(key=lambda b: 1 if b[1] == "cancel" else 0)
        self._default = None
        for label, role in ordered:
            b = QPushButton(label.replace("&", "&&"))
            b.setObjectName({"primary": "alertPrimary",
                             "destructive": "alertDestructive"}
                            .get(role, "alertButton"))
            b.setMinimumHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Fixed)
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, lb=label: self._choose(lb))
            row.addWidget(b)
            if role == "primary" and self._default is None:
                self._default = b
            if role == "cancel":
                self._cancel_label = label
        if self._default is not None:
            self._default.setDefault(True)
            self._default.setFocus()
        lay.addLayout(row)
        self.adjustSize()

    def _choose(self, label):
        self.result_label = label
        self.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.result_label = None
            self.reject()
            return
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._default:
            self._default.click()
            return
        super().keyPressEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        host = self.parentWidget().window() if self.parentWidget() else None
        if host is not None and host.isVisible():
            g = host.frameGeometry()
            self.move(g.center().x() - self.width() // 2,
                      g.top() + max(60, g.height() // 2 - self.height() // 2 - 40))
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center() - self.rect().center())
        self.setWindowOpacity(0.0)
        anim = QPropertyAnimation(self, b"windowOpacity", self)
        anim.setDuration(140)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim


def alert(parent, title, message="", buttons=None, kind="info", detail=None):
    """Show a modal alert; returns the clicked label or None if dismissed."""
    buttons = buttons or [("OK", "primary")]
    dlg = MacAlert(parent, title, message, buttons, kind, detail)
    host = parent.window() if parent is not None else None
    dim = _Dim(host) if host is not None and host.isVisible() else None
    try:
        dlg.exec()
    finally:
        if dim is not None:
            dim.deleteLater()
    if dlg.result_label is None or dlg.result_label == dlg._cancel_label:
        return None
    return dlg.result_label


def info(parent, title, message="", detail=None, kind="info"):
    alert(parent, title, message, [("OK", "primary")], kind, detail)


def warn(parent, title, message="", detail=None):
    alert(parent, title, message, [("OK", "primary")], "warning", detail)


def error(parent, title, message="", detail=None):
    alert(parent, title, message, [("OK", "primary")], "error", detail)


def confirm(parent, title, message="", ok="OK", cancel="Cancel",
            destructive=False, kind="question", detail=None):
    """Two-button confirmation; True when the action button was clicked."""
    role = "destructive" if destructive else "primary"
    return alert(parent, title, message,
                 [(cancel, "cancel"), (ok, role)], kind, detail) == ok
