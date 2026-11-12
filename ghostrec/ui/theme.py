"""macOS-style theme (light + dark) for the GhostRec desktop UI.

Colors follow Apple's system palette (systemBlue, systemRed, label colors,
grouped backgrounds) so the app reads like a native macOS utility, while
still running on Windows with Qt.

Other modules read colors as ``theme.NAME`` at *call* time, so switching the
appearance at runtime (``apply(app, "dark")``) updates everything that paints
itself; widgets with cached inline styles expose a ``restyle()`` hook.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from ghostrec.ui import branding

FONT_UI = '"SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif'
FONT_DISPLAY = ('"SF Pro Display", "Segoe UI Variable Display", "Segoe UI", '
                '"Inter", sans-serif')
FONT_MONO = '"SF Mono", "Cascadia Mono", "Consolas", monospace'

DARK = {
    "MODE": "dark",
    # surfaces
    "BG": "#1e1e1e",            # window content
    "BG_SIDEBAR": "#2a2a2c",    # source list (vibrant sidebar look)
    "BG_TOOLBAR": "#1e1e1e",
    "BG_ALT": "#232325",        # alternate rows / list bg
    "BG_CARD": "#2c2c2e",       # secondarySystemGroupedBackground
    "BG_ELEVATED": "#3a3a3c",
    "BG_INPUT": "#1c1c1e",
    "BG_CONTROL": "#48484a",    # push button face
    "BG_CONTROL_HOVER": "#545456",
    "BG_CONTROL_PRESSED": "#5e5e60",
    "BORDER": "#3d3d3f",
    "BORDER_SOFT": "#2f2f31",
    "SEPARATOR": "#0f0f10",
    # labels
    "TEXT": "#f5f5f7",
    "MUTED": "#98989d",         # secondaryLabel
    "DIMMED": "#6e6e73",        # tertiaryLabel
    "FILL": "#3a3a3c",          # quaternary fill (meter off, tracks)
    # system colors
    "ACCENT": "#0a84ff",
    "ACCENT_HOVER": "#409cff",
    "ACCENT_PRESSED": "#0071e3",
    "OK": "#30d158",
    "WARN": "#ff9f0a",
    "ERR": "#ff453a",
    "IDLE": "#8e8e93",
    "SELECTION": "#0a84ff",
    "SELECTION_TEXT": "#ffffff",
    "SIDEBAR_SELECTION": "#464649",
    "PREVIEW_BG": "#0b0b0c",
    # traffic lights
    "TL_CLOSE": "#ff5f57", "TL_MIN": "#febc2e", "TL_ZOOM": "#28c840",
    "TL_INACTIVE": "#4d4d50", "TL_GLYPH": "#4d0000",
}

LIGHT = {
    "MODE": "light",
    "BG": "#ffffff",
    "BG_SIDEBAR": "#ececee",
    "BG_TOOLBAR": "#ffffff",
    "BG_ALT": "#f5f5f7",
    "BG_CARD": "#f5f5f7",
    "BG_ELEVATED": "#ffffff",
    "BG_INPUT": "#ffffff",
    "BG_CONTROL": "#ffffff",
    "BG_CONTROL_HOVER": "#f5f5f7",
    "BG_CONTROL_PRESSED": "#e8e8ed",
    "BORDER": "#d2d2d7",
    "BORDER_SOFT": "#e5e5ea",
    "SEPARATOR": "#dcdce0",
    "TEXT": "#1d1d1f",
    "MUTED": "#6e6e73",
    "DIMMED": "#a1a1a6",
    "FILL": "#e5e5ea",
    "ACCENT": "#007aff",
    "ACCENT_HOVER": "#1a88ff",
    "ACCENT_PRESSED": "#0062cc",
    "OK": "#28a745",
    "WARN": "#ff9500",
    "ERR": "#ff3b30",
    "IDLE": "#8e8e93",
    "SELECTION": "#007aff",
    "SELECTION_TEXT": "#ffffff",
    "SIDEBAR_SELECTION": "#d6d6db",
    "PREVIEW_BG": "#1d1d1f",
    "TL_CLOSE": "#ff5f57", "TL_MIN": "#febc2e", "TL_ZOOM": "#28c840",
    "TL_INACTIVE": "#d1d1d6", "TL_GLYPH": "#4d0000",
}

# --- module-level tokens (overwritten by _use) ----------------------------- #
MODE = "dark"
BG = BG_SIDEBAR = BG_TOOLBAR = BG_ALT = BG_CARD = BG_ELEVATED = BG_INPUT = ""
BG_CONTROL = BG_CONTROL_HOVER = BG_CONTROL_PRESSED = ""
BORDER = BORDER_SOFT = SEPARATOR = TEXT = MUTED = DIMMED = FILL = ""
ACCENT = ACCENT_HOVER = ACCENT_PRESSED = OK = WARN = ERR = IDLE = ""
SELECTION = SELECTION_TEXT = SIDEBAR_SELECTION = PREVIEW_BG = ""
TL_CLOSE = TL_MIN = TL_ZOOM = TL_INACTIVE = TL_GLYPH = ""
# tinted state colors (computed)
OK_BG = OK_BORDER = REC_BG = REC_BORDER = WARN_BG = WARN_BORDER = ""
IDLE_BG = IDLE_BORDER = ACCENT_MUTED = ""


def rgba(hex_color, alpha):
    """'#rrggbb' + 0..1 alpha -> 'rgba(r, g, b, a)' for QSS."""
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


def _use(palette):
    g = globals()
    g.update(palette)
    a_bg, a_border = (0.16, 0.38) if palette["MODE"] == "dark" else (0.12, 0.35)
    g["OK_BG"], g["OK_BORDER"] = rgba(OK, a_bg), rgba(OK, a_border)
    g["REC_BG"], g["REC_BORDER"] = rgba(ERR, a_bg), rgba(ERR, a_border)
    g["WARN_BG"], g["WARN_BORDER"] = rgba(WARN, a_bg), rgba(WARN, a_border)
    g["IDLE_BG"], g["IDLE_BORDER"] = rgba(IDLE, 0.14), rgba(IDLE, 0.30)
    g["ACCENT_MUTED"] = rgba(ACCENT, a_bg)


_use(DARK)


def is_dark():
    return MODE == "dark"


def resolve_mode(appearance="auto"):
    """'auto' | 'light' | 'dark' -> 'light' | 'dark' (auto follows the OS)."""
    if appearance in ("light", "dark"):
        return appearance
    app = QApplication.instance()
    if app is not None:
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return "light"
            if scheme == Qt.ColorScheme.Dark:
                return "dark"
        except AttributeError:  # Qt < 6.5
            pass
    return "dark"


def _url(path):
    return str(path).replace("\\", "/")


def build_qss():
    check = _url(branding.ASSETS / "check.svg")
    chevrons = _url(branding.ASSETS / "chevrons.svg")
    chevron_up = _url(branding.ASSETS / ("chevron-up-light.svg" if is_dark()
                                         else "chevron-up-dark.svg"))
    chevron_down = _url(branding.ASSETS / ("chevron-down-light.svg" if is_dark()
                                           else "chevron-down-dark.svg"))
    control_border = BORDER if is_dark() else "#c7c7cc"
    hover_row = rgba(TEXT, 0.05)
    return f"""
QWidget {{
    font-family: {FONT_UI};
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget#centralWidget, QWidget#contentPane {{ background: {BG}; }}
QStackedWidget, QStackedWidget > QWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollArea {{ border: none; }}

/* ---- window chrome ------------------------------------------------------ */
QWidget#sidebarPane {{
    background: {BG_SIDEBAR};
    border-right: 1px solid {SEPARATOR};
}}
QWidget#toolbar {{
    background: {BG_TOOLBAR};
    border-bottom: 1px solid {BORDER_SOFT};
}}
QLabel#toolbarTitle {{
    font-family: {FONT_DISPLAY};
    font-size: 15px; font-weight: 700; color: {TEXT};
}}
QLabel#toolbarSubtitle {{ color: {MUTED}; font-size: 11px; }}
QLabel#sidebarSection {{
    color: {DIMMED}; font-size: 11px; font-weight: 600;
    padding: 0 0 0 4px;
}}
QLabel#brandTitle {{
    font-family: {FONT_DISPLAY};
    color: {TEXT}; font-size: 13px; font-weight: 700;
}}
QLabel#brandSubtitle {{ color: {MUTED}; font-size: 11px; }}

QListWidget#sidebar {{
    background: transparent; border: none; outline: none;
    padding: 0 10px;
}}
QListWidget#sidebar::item {{
    color: {TEXT}; padding: 6px 8px; margin: 1px 0;
    border-radius: 6px; border: none;
}}
QListWidget#sidebar::item:hover {{ background: {rgba(TEXT, 0.06)}; }}
QListWidget#sidebar::item:selected {{
    background: {SIDEBAR_SELECTION}; color: {TEXT};
}}

/* ---- typography --------------------------------------------------------- */
QLabel#pageSubtitle, QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#dimmed {{ color: {DIMMED}; font-size: 11px; }}
QLabel#sectionLabel {{
    color: {MUTED}; font-size: 11px; font-weight: 600;
}}
QLabel#bigTimer {{
    font-family: {FONT_DISPLAY};
    color: {TEXT}; font-size: 44px; font-weight: 300;
}}
QLabel#recBadge {{
    background: {REC_BG}; color: {ERR}; border: 1px solid {REC_BORDER};
    border-radius: 9px; padding: 1px 8px; font-size: 10px; font-weight: 700;
}}
QLabel#sectionHeader {{
    font-family: {FONT_DISPLAY}; color: {TEXT};
    font-size: 13px; font-weight: 700;
}}
QLabel#rowLabel {{ color: {TEXT}; font-size: 12px; }}
QFrame#hairline {{ background: {BORDER_SOFT}; border: none; }}
QWidget#groupCard {{
    background: {rgba(TEXT, 0.045)}; border: 1px solid {BORDER_SOFT};
    border-radius: 9px;
}}
QWidget#inspectorBody {{ background: transparent; }}
QWidget#inspectorFooter {{
    background: transparent; border-top: 1px solid {BORDER_SOFT};
    border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
}}
QLabel#noticeIconWarn {{ color: {WARN}; font-size: 15px; background: transparent; }}
QLabel#noticeIconOk {{ color: {OK}; font-size: 15px; font-weight: 700;
    background: transparent; }}
QWidget#resultBox {{
    background: {OK_BG}; border: 1px solid {OK_BORDER}; border-radius: 10px;
}}
QLabel#resultText {{ color: {TEXT}; background: transparent; }}
QPushButton#closeButton {{
    background: transparent; border: none; color: {MUTED};
    border-radius: 11px; padding: 0; min-height: 0; font-size: 11px;
}}
QPushButton#closeButton:hover {{ background: {rgba(TEXT, 0.10)}; color: {TEXT}; }}
QLabel#mono {{
    color: {MUTED}; font-size: 11px; font-family: {FONT_MONO};
}}

/* ---- push buttons ------------------------------------------------------- */
QPushButton {{
    background: {BG_CONTROL}; color: {TEXT};
    border: 1px solid {control_border};
    border-radius: 6px; padding: 4px 14px; min-height: 20px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {BG_CONTROL_HOVER}; }}
QPushButton:pressed, QPushButton:checked {{ background: {BG_CONTROL_PRESSED}; }}
QPushButton:disabled {{
    color: {DIMMED}; background: {rgba(BG_CONTROL, 0.5)};
    border-color: {BORDER_SOFT};
}}
QPushButton#primary {{
    background: {ACCENT}; color: white; border: 1px solid {ACCENT_PRESSED};
    font-weight: 600; padding: 5px 18px;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#primary:disabled {{
    background: {FILL}; color: {DIMMED}; border-color: {FILL};
}}
QPushButton#danger {{
    background: {ERR}; color: white; border: 1px solid {ERR};
    font-weight: 600; padding: 5px 18px;
}}
QPushButton#danger:hover {{ background: {rgba(ERR, 0.85)}; }}
QPushButton#danger:disabled {{
    background: {FILL}; color: {DIMMED}; border-color: {FILL};
}}
QPushButton#accent {{
    background: {ACCENT_MUTED}; color: {ACCENT}; border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton#accent:hover {{ background: {rgba(ACCENT, 0.24)}; }}
QPushButton#accent:pressed {{ background: {rgba(ACCENT, 0.32)}; }}
QPushButton#ghost {{
    background: transparent; border-color: transparent; color: {MUTED};
}}
QPushButton#ghost:hover {{ background: {rgba(TEXT, 0.06)}; color: {TEXT}; }}

/* ---- text fields / popups ----------------------------------------------- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT}; color: {TEXT};
    border: 1px solid {control_border}; border-radius: 6px;
    padding: 4px 8px; min-height: 20px;
    selection-background-color: {ACCENT}; selection-color: white;
}}
QLineEdit#searchField {{
    border-radius: 7px; padding-left: 10px; background: {rgba(TEXT, 0.06)};
    border: 1px solid transparent;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {rgba(ACCENT, 0.75)}; padding: 3px 7px;
}}
QLineEdit#searchField:focus {{ padding-left: 9px; background: {BG_INPUT}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none; background: transparent; width: 16px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({chevron_up}); width: 8px; height: 5px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({chevron_down}); width: 8px; height: 5px;
}}
QComboBox {{
    background: {BG_CONTROL}; color: {TEXT};
    border: 1px solid {control_border}; border-radius: 6px;
    padding: 4px 30px 4px 9px; min-height: 20px;
}}
QComboBox:hover {{ background: {BG_CONTROL_HOVER}; }}
QComboBox:disabled {{ color: {DIMMED}; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 16px; height: 16px; margin-right: 4px;
    border: none; border-radius: 4px; background: {ACCENT};
}}
QComboBox::drop-down:disabled {{ background: {FILL}; }}
QComboBox::down-arrow {{ image: url({chevrons}); width: 8px; height: 11px; }}
QComboBox QAbstractItemView {{
    background: {BG_ELEVATED}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 4px;
    outline: none;
    selection-background-color: {ACCENT}; selection-color: white;
}}

QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px;
    background: {BG_CONTROL}; border: 1px solid {control_border};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border-color: {ACCENT};
    image: url({check});
}}

/* ---- lists & tables ----------------------------------------------------- */
QListWidget, QTreeWidget, QTableWidget {{
    background: {BG_ALT}; color: {TEXT};
    border: 1px solid {BORDER_SOFT}; border-radius: 10px; outline: none;
    alternate-background-color: {rgba(TEXT, 0.03)};
}}
QListWidget::item, QTreeWidget::item {{
    padding: 4px 8px; border-radius: 6px;
}}
QTableWidget::item {{ padding: 4px 8px; border: none; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background: {hover_row}; }}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {{
    background: {SELECTION}; color: {SELECTION_TEXT};
}}
QListWidget#activityFeed {{
    font-family: {FONT_MONO}; font-size: 11px;
}}
QListWidget#activityFeed::item {{ padding: 2px 6px; }}
QListWidget#activityFeed::item:hover {{ background: transparent; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background: transparent; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER_SOFT};
    border-right: 1px solid {BORDER_SOFT};
    padding: 6px 10px; font-size: 11px; font-weight: 600;
}}
QHeaderView::section:last {{ border-right: none; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

/* ---- cards / callouts --------------------------------------------------- */
QWidget#statusPill {{ border-radius: 11px; }}
QWidget#adviceBox, QWidget#inspector {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 12px;
}}
QLabel#preview {{
    background: {PREVIEW_BG}; color: #8e8e93;
    border: 1px solid {BORDER_SOFT}; border-radius: 12px;
}}
QLabel#banner {{
    background: {REC_BG}; color: {TEXT}; border: 1px solid {REC_BORDER};
    border-radius: 8px; padding: 8px 12px;
}}
QLabel#silenceBanner {{
    background: {WARN_BG}; color: {TEXT}; border: 1px solid {WARN_BORDER};
    border-radius: 8px; padding: 8px 12px; font-weight: 600;
}}
QLabel#details {{
    background: {BG_CARD}; color: {MUTED}; border: 1px solid {BORDER_SOFT};
    border-radius: 10px; padding: 10px 12px;
}}
QLabel#cardTitle {{ color: {TEXT}; font-size: 13px; font-weight: 600; }}
QLabel#adviceText {{ color: {TEXT}; font-size: 12px; background: transparent; }}
QWidget#adviceBox {{
    background: {WARN_BG}; border: 1px solid {WARN_BORDER}; border-radius: 10px;
}}

/* ---- grouped settings (System Settings style) --------------------------- */
QGroupBox {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 10px;
    margin-top: 22px; padding: 12px 14px 10px 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 4px; top: 0px; padding: 0 0 4px 0;
    color: {TEXT}; font-size: 13px; font-weight: 700;
}}
QGroupBox QLabel {{ background: transparent; }}

/* ---- scrollbars (overlay style) ----------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {rgba(TEXT, 0.25)}; min-height: 28px; border-radius: 3px;
    margin: 0 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {rgba(TEXT, 0.4)}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {rgba(TEXT, 0.25)}; min-width: 28px; border-radius: 3px;
    margin: 2px 0;
}}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    background: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px 8px; border-radius: 6px;
}}
QMenu {{
    background: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 5px;
}}
QMenu::item {{ padding: 4px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {ACCENT}; color: white; }}
QMenu::item:disabled {{ color: {DIMMED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}
QMessageBox {{ background: {BG}; }}

/* ---- Record page gallery --------------------------------------------- */
QLabel#heroTitle {{
    font-family: {FONT_DISPLAY}; color: {TEXT};
    font-size: 22px; font-weight: 700;
}}
QWidget#segmented {{
    background: {rgba(TEXT, 0.07)}; border-radius: 8px;
}}
QPushButton#segment {{
    background: transparent; border: none; color: {MUTED};
    border-radius: 6px; padding: 3px 12px; min-height: 18px;
    font-size: 12px; font-weight: 500;
}}
QPushButton#segment:hover {{ color: {TEXT}; }}
QPushButton#segment:checked {{
    background: {BG_CONTROL if is_dark() else "#ffffff"}; color: {TEXT};
    font-weight: 600; border: 1px solid {rgba(TEXT, 0.08)};
}}
QPushButton#iconButton {{
    padding: 0; font-size: 15px; border-radius: 7px; min-height: 0;
}}
QListWidget#windowGrid {{
    background: transparent; border: none; padding: 0;
}}
QListWidget#windowGrid::item {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOFT};
    border-radius: 14px;
}}
QListWidget#windowGrid::item:hover {{
    border: 1px solid {rgba(ACCENT, 0.55)};
    background: {rgba(ACCENT, 0.06)};
}}
QListWidget#windowGrid::item:selected {{
    background: {ACCENT_MUTED}; border: 2px solid {ACCENT};
}}
QLabel#tileThumb {{
    background: {PREVIEW_BG}; border-radius: 9px; color: #8e8e93;
    font-size: 11px;
}}
QLabel#tileTitle {{ color: {TEXT}; font-size: 12px; font-weight: 600;
    background: transparent; }}
QLabel#tileMeta {{ color: {MUTED}; font-size: 11px; background: transparent; }}
QLabel#tileBadgeWarn {{
    background: {WARN_BG}; color: {WARN}; border-radius: 8px;
    padding: 1px 7px; font-size: 10px; font-weight: 700;
}}
QLabel#tileBadgeOk {{
    background: {OK_BG}; color: {OK}; border-radius: 8px;
    padding: 1px 7px; font-size: 10px; font-weight: 700;
}}
QLabel#bigThumb {{
    background: {PREVIEW_BG}; border-radius: 10px; color: #8e8e93;
    border: 1px solid {BORDER_SOFT};
}}
QPushButton#linkButton {{
    background: transparent; border: none; color: {ACCENT};
    font-weight: 600; padding: 0 2px; min-height: 0;
}}
QPushButton#linkButton:hover {{ text-decoration: underline; }}
QPushButton#recordButton {{
    background: {ERR}; color: white; border: none; border-radius: 20px;
    font-size: 14px; font-weight: 700; padding: 0 18px;
    min-height: 40px; max-height: 40px;
}}
QPushButton#recordButton:hover {{ background: {rgba(ERR, 0.88)}; }}
QPushButton#recordButton:pressed {{ background: {rgba(ERR, 0.75)}; }}
QPushButton#recordButton:disabled {{ background: {FILL}; color: {DIMMED}; }}

/* ---- Activity log ----------------------------------------------------- */
QLabel#logTime {{ color: {DIMMED}; font-family: {FONT_MONO}; font-size: 11px;
    background: transparent; }}
QLabel#logTag {{
    background: {rgba(TEXT, 0.07)}; color: {MUTED}; border-radius: 5px;
    padding: 1px 6px; font-size: 10px; font-weight: 600;
}}
QLabel#logText {{ color: {TEXT}; font-size: 12px; background: transparent; }}
QLabel#logWarn {{ color: {WARN}; font-size: 12px; background: transparent; }}
QLabel#logError {{ color: {ERR}; font-size: 12px; font-weight: 600;
    background: transparent; }}
QLabel#emptyState {{
    color: {DIMMED}; background: {BG_ALT}; border: 1px dashed {BORDER};
    border-radius: 10px; font-size: 12px;
}}

/* ---- macOS alert (ghostrec.ui.dialogs) ---------------------------------- */
QWidget#alertCard {{
    background: {BG_ELEVATED if is_dark() else "#ffffff"};
    border: 1px solid {rgba(TEXT, 0.12)}; border-radius: 14px;
}}
QLabel#alertTitle {{
    font-family: {FONT_DISPLAY}; color: {TEXT};
    font-size: 14px; font-weight: 700; background: transparent;
}}
QLabel#alertText {{ color: {TEXT}; font-size: 12px; background: transparent; }}
QLabel#alertDetail {{
    color: {MUTED}; font-size: 11px; background: {rgba(TEXT, 0.05)};
    border-radius: 6px; padding: 8px 10px;
}}
QPushButton#alertButton, QPushButton#alertPrimary, QPushButton#alertDestructive {{
    border-radius: 7px; padding: 5px 12px; font-weight: 500;
}}
QPushButton#alertButton {{
    background: {rgba(TEXT, 0.10)}; color: {TEXT}; border: none;
}}
QPushButton#alertButton:hover {{ background: {rgba(TEXT, 0.16)}; }}
QPushButton#alertPrimary {{
    background: {ACCENT}; color: white; border: none; font-weight: 600;
}}
QPushButton#alertPrimary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#alertPrimary:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton#alertDestructive {{
    background: {rgba(TEXT, 0.10)}; color: {ERR}; border: none; font-weight: 600;
}}
QPushButton#alertDestructive:hover {{ background: {rgba(ERR, 0.16)}; }}
QDialog {{ background: {BG}; }}
"""


def apply(app: QApplication, appearance="auto") -> str:
    """Apply the palette + stylesheet. Returns the resolved mode."""
    mode = resolve_mode(appearance)
    _use(DARK if mode == "dark" else LIGHT)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_INPUT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_ALT))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_CONTROL))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(DIMMED))
    disabled = QColor(DIMMED)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    app.setPalette(pal)
    app.setStyleSheet(build_qss())
    return mode
