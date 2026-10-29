"""Logo assets and QIcon helpers.

The mark: viewfinder brackets clamping a ghost = the window stays pinned by
HWND; the red dot = recording. Source files live in ``ghostrec/ui/assets/``.
"""

import sys
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
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
ICON_SVG = ASSETS / "icon.svg"            # white mark, transparent
ICON_DARK_SVG = ASSETS / "icon-dark.svg"  # mark on the graphite plate
ICON_LIGHT_SVG = ASSETS / "icon-light.svg"  # graphite mark, transparent
MARK_MONO_SVG = ASSETS / "mark-mono.svg"
TRAY_IDLE_SVG = ASSETS / "tray-idle.svg"  # plate mark without the REC dot

REC_COLOR = "#FF453A"
BADGE_EDGE = "#0A0B0F"

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
def tray_icon(recording: bool = False) -> QIcon:
    """Tray icon: plate mark, with a REC badge when recording."""
    base = TRAY_IDLE_SVG if TRAY_IDLE_SVG.exists() else ICON_DARK_SVG
    icon = QIcon()
    for size in _TRAY_SIZES:
        pm = QPixmap(_render(base, size))
        if recording:
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(REC_COLOR))
            d = size * 0.42
            p.drawEllipse(QRectF(size - d, size - d, d, d))
            p.end()
        icon.addPixmap(pm)
    return icon
