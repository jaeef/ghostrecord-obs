"""Windows 11 window styling + Fluent icon-font glyphs.

The native title bar is kept; DWM recolors it to match the app.
"""

import ctypes
import sys

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

from ghostrec.ui import theme

# Segoe Fluent Icons / MDL2 code points
GLYPHS = {
    "record": "\uE7C8",
    "live": "\uE714",
    "library": "\uE8F1",
    "settings": "\uE713",
    "refresh": "\uE72C",
    "close": "\uE711",
    "warning": "\uE7BA",
    "check": "\uE73E",
    "error": "\uEA39",
    "info": "\uE946",
    "copy": "\uE8C8",
    "delete": "\uE74D",
}
ICON_SIZE = QSize(18, 18)

_DWMWA_DARK = 20
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def _colorref(hex_color):
    c = QColor(hex_color)
    return c.red() | (c.green() << 8) | (c.blue() << 16)


def style_window(window):
    """Dark/light title bar in the app's colors. Silently a no-op before
    Windows 11 (the attributes simply are not supported)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.c_void_p(int(window.winId()))
        dwm = ctypes.windll.dwmapi

        def put(attr, value):
            v = ctypes.c_uint(value)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v),
                                      ctypes.sizeof(v))

        put(_DWMWA_DARK, 1 if theme.is_dark() else 0)
        put(_DWMWA_CAPTION_COLOR, _colorref(theme.BG_SIDEBAR))
        put(_DWMWA_TEXT_COLOR, _colorref(theme.TEXT))
    except Exception:
        pass


def glyph_icon(name, color=None, size=18):
    """QIcon from a Fluent icon-font glyph."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont("Segoe Fluent Icons")
    font.setFamilies(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
    font.setPixelSize(int(size * 0.9))
    p.setFont(font)
    p.setPen(QColor(color or theme.ACCENT_FG))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter,
               GLYPHS[name])
    p.end()
    return QIcon(pm)
