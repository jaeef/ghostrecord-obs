"""Logo assets and QIcon helpers.

The mark: viewfinder brackets clamping a ghost = the window stays pinned by
HWND; the red dot = recording. Source files live in ``ghostrec/ui/assets/``.
"""

import sys
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtSvg import QSvgRenderer


def _assets_dir() -> Path:
    """Assets folder in a dev checkout and in a frozen (PyInstaller) build."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        for candidate in (Path(bundle) / "ghostrec" / "ui" / "assets",
                          Path(bundle) / "assets"):
            if candidate.is_dir():
                return candidate
    return Path(__file__).resolve().parent / "assets"


ASSETS = _assets_dir()

ICON_ICO = ASSETS / "app.ico"
ICON_DARK_SVG = ASSETS / "icon-dark.svg"  # mark on the graphite plate
TRAY_IDLE_SVG = ASSETS / "tray-idle.svg"  # plate mark without the REC dot

REC_COLOR = "#FF453A"       # OBS-style recording dot
WARN_COLOR = "#FCE100"      # recording at risk (minimized, may freeze)

# Sizes Windows asks for: tray (16-24), alt-tab (32), taskbar (48+).
_TRAY_SIZES = (16, 20, 24, 32, 48, 64)


def _render(svg_path: Path, size: int) -> QPixmap:
    """Rasterize an SVG asset to a square pixmap (transparent if missing)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if not svg_path.exists():
        return pm
    renderer = QSvgRenderer(str(svg_path))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    return pm


@lru_cache(maxsize=8)
def logo_pixmap(size: int = 32) -> QPixmap:
    """Plate version of the mark — used in the sidebar brand."""
    return _render(ICON_DARK_SVG, size)


def app_icon() -> QIcon:
    """Application / window icon. Prefers the multi-size .ico."""
    if ICON_ICO.exists():
        return QIcon(str(ICON_ICO))
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_render(ICON_DARK_SVG, size))
    return icon

@lru_cache(maxsize=4)
def status_icon(state=None) -> QIcon:
    """Logo with an OBS-style dot: red while recording, yellow when the
    recording is at risk. ``state=None`` is the plain mark (no dot).

    Used for the window (title bar + taskbar) and the tray.
    """
    base = TRAY_IDLE_SVG if TRAY_IDLE_SVG.exists() else ICON_DARK_SVG
    color = {"rec": REC_COLOR, "warn": WARN_COLOR}.get(state)
    icon = QIcon()
    for size in _TRAY_SIZES:
        pm = QPixmap(_render(base, size))
        if color:
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            d = size * 0.46
            rect = QRectF(size - d, size - d, d, d)
            # dark ring keeps the dot visible on light taskbars (yellow!)
            p.setPen(QPen(QColor("#1b1b1b"), max(1.0, size / 24)))
            p.setBrush(QColor(color))
            p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
            p.end()
        icon.addPixmap(pm)
    return icon
