"""macOS-style window chrome for a frameless Qt window on Windows.

* ``TrafficLights``  — close / minimize / zoom buttons (glyphs on hover)
* ``DragRegion``     — any empty area that moves the window; double-click zooms
* ``FramelessResizer`` — edge/corner resize for a frameless window
* ``apply_native_effects`` — Windows 11 rounded corners + shadow via DWM
* ``sidebar_icon``   — SF-Symbols-like line icons for the source list
"""

import ctypes
import sys

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QCursor, QIcon, QPainter, QPainterPath, QPen,
                         QPixmap)
from PyQt6.QtWidgets import QApplication, QWidget

from ghostrec.ui import theme


class TrafficLights(QWidget):
    """The three macOS window buttons. Glyphs appear while hovering the group."""

    close_clicked = pyqtSignal()
    minimize_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()

    D = 12      # button diameter
    GAP = 8     # spacing between buttons

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.D * 3 + self.GAP * 2 + 2, self.D + 4)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._hover = False
        self._pressed = -1
        self.setToolTip("")

    def _rect(self, i):
        return QRectF(1 + i * (self.D + self.GAP), 2, self.D, self.D)

    def _hit(self, pos):
        for i in range(3):
            if self._rect(i).adjusted(-2, -2, 2, 2).contains(QPointF(pos)):
                return i
        return -1

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self._pressed = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = self._hit(e.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, e):
        hit = self._hit(e.position().toPoint())
        pressed, self._pressed = self._pressed, -1
        self.update()
        if e.button() != Qt.MouseButton.LeftButton or hit < 0 or hit != pressed:
            return
        (self.close_clicked, self.minimize_clicked, self.zoom_clicked)[hit].emit()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self.window().isActiveWindow() or self._hover
        colors = (theme.TL_CLOSE, theme.TL_MIN, theme.TL_ZOOM)
        for i, base in enumerate(colors):
            r = self._rect(i)
            fill = QColor(base if active else theme.TL_INACTIVE)
            if self._pressed == i:
                fill = fill.darker(125)
            p.setPen(QPen(fill.darker(118), 0.6))
            p.setBrush(fill)
            p.drawEllipse(r)
            if not self._hover:
                continue
            glyph = QColor(0, 0, 0, 150)
            p.setPen(QPen(glyph, 1.25, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap))
            c = r.center()
            k = 2.6
            if i == 0:      # ×
                p.drawLine(QPointF(c.x() - k, c.y() - k), QPointF(c.x() + k, c.y() + k))
                p.drawLine(QPointF(c.x() - k, c.y() + k), QPointF(c.x() + k, c.y() - k))
            elif i == 1:    # −
                p.drawLine(QPointF(c.x() - k - 0.6, c.y()), QPointF(c.x() + k + 0.6, c.y()))
            else:           # zoom: two triangles
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(glyph)
                a = QPainterPath()
                a.moveTo(c.x() - 3.2, c.y() - 3.2)
                a.lineTo(c.x() + 1.2, c.y() - 3.2)
                a.lineTo(c.x() - 3.2, c.y() + 1.2)
                a.closeSubpath()
                b = QPainterPath()
                b.moveTo(c.x() + 3.2, c.y() + 3.2)
                b.lineTo(c.x() - 1.2, c.y() + 3.2)
                b.lineTo(c.x() + 3.2, c.y() - 1.2)
                b.closeSubpath()
                p.drawPath(a)
                p.drawPath(b)
        p.end()


class DragRegion(QWidget):
    """A widget whose empty background drags the window (title-bar behavior)."""

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            toggle_zoom(self.window())
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


def toggle_zoom(win):
    if win.isMaximized():
        win.showNormal()
    else:
        win.showMaximized()


class FramelessResizer(QObject):
    """Edge/corner resizing for a frameless top-level window.

    Installed as an application event filter so it works no matter which
    child widget sits under the window border.
    """

    MARGIN = 6

    def __init__(self, window):
        super().__init__(window)
        self._win = window
        self._cursor_set = False
        QApplication.instance().installEventFilter(self)

    def _edges(self, global_pos):
        w = self._win
        if w.isMaximized() or w.isFullScreen():
            return Qt.Edge(0)
        g = w.frameGeometry()
        x, y, m = global_pos.x(), global_pos.y(), self.MARGIN
        if not g.adjusted(-1, -1, 1, 1).contains(global_pos):
            return Qt.Edge(0)
        edges = Qt.Edge(0)
        if x <= g.left() + m:
            edges |= Qt.Edge.LeftEdge
        elif x >= g.right() - m:
            edges |= Qt.Edge.RightEdge
        if y <= g.top() + m:
            edges |= Qt.Edge.TopEdge
        elif y >= g.bottom() - m:
            edges |= Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges):
        L, R = Qt.Edge.LeftEdge, Qt.Edge.RightEdge
        T, B = Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if edges in (L | T, R | B):
            return Qt.CursorShape.SizeFDiagCursor
        if edges in (R | T, L | B):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (L | R):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _set_cursor(self, edges):
        if edges:
            shape = self._cursor_for(edges)
            if self._cursor_set:
                QApplication.changeOverrideCursor(QCursor(shape))
            else:
                QApplication.setOverrideCursor(QCursor(shape))
                self._cursor_set = True
        elif self._cursor_set:
            QApplication.restoreOverrideCursor()
            self._cursor_set = False

    def eventFilter(self, obj, event):
        et = event.type()
        if et not in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                      QEvent.Type.HoverMove):
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self._win:
            return False
        if QApplication.activePopupWidget() is not None:
            return False
        gp = QCursor.pos()
        edges = self._edges(gp)
        if et == QEvent.Type.MouseButtonPress:
            if edges and event.button() == Qt.MouseButton.LeftButton:
                handle = self._win.windowHandle()
                if handle is not None and handle.startSystemResize(edges):
                    return True
            return False
        if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._set_cursor(edges)
        return False


def apply_native_effects(window, dark=True):
    """Ask DWM (Windows 11) for rounded corners, shadow and dark borders.

    Silently does nothing on other platforms / older Windows builds.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        dwm = ctypes.windll.dwmapi

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr,
                                      ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 1 if dark else 0)   # DWMWA_USE_IMMERSIVE_DARK_MODE
        set_attr(33, 2)                  # DWMWA_WINDOW_CORNER_PREFERENCE=ROUND
        # A 1px DWM frame restores the native drop shadow on popup windows.

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                        ("t", ctypes.c_int), ("b", ctypes.c_int)]
        m = MARGINS(1, 1, 1, 1)
        dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(hwnd), ctypes.byref(m))
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Sidebar icons                                                                #
# --------------------------------------------------------------------------- #

def sidebar_icon(kind, color=None, size=18):
    """Small line icon drawn in code: 'record' | 'live' | 'library' | 'settings'."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    col = QColor(color or theme.ACCENT)
    pen = QPen(col, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
               Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = float(size)
    c = QPointF(s / 2, s / 2)
    if kind == "record":
        p.drawEllipse(c, s * 0.38, s * 0.38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(c, s * 0.2, s * 0.2)
    elif kind == "live":
        p.setBrush(col)
        p.drawEllipse(c, s * 0.09, s * 0.09)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for r, span in ((0.24, 100), (0.4, 100)):
            rect = QRectF(c.x() - s * r, c.y() - s * r, 2 * s * r, 2 * s * r)
            p.drawArc(rect, int(-50 * 16), int(span * 16))
            p.drawArc(rect, int(130 * 16), int(span * 16))
    elif kind == "library":
        p.drawRoundedRect(QRectF(s * 0.12, s * 0.22, s * 0.76, s * 0.6), 2.5, 2.5)
        p.drawLine(QPointF(s * 0.26, s * 0.12), QPointF(s * 0.74, s * 0.12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        tri = QPainterPath()
        tri.moveTo(s * 0.43, s * 0.39)
        tri.lineTo(s * 0.62, s * 0.52)
        tri.lineTo(s * 0.43, s * 0.65)
        tri.closeSubpath()
        p.drawPath(tri)
    elif kind == "settings":
        for i, y in enumerate((0.25, 0.5, 0.75)):
            p.drawLine(QPointF(s * 0.12, s * y), QPointF(s * 0.88, s * y))
            kx = (0.65, 0.35, 0.58)[i]
            p.setBrush(QColor(theme.BG_SIDEBAR))
            p.drawEllipse(QPointF(s * kx, s * y), s * 0.1, s * 0.1)
    p.end()
    return QIcon(pm)


ICON_SIZE = QSize(18, 18)
