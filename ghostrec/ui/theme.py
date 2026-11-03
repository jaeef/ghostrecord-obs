"""Neutral dark shadcn-inspired theme for the GhostRec desktop UI."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# Keep the palette intentionally restrained: zinc surfaces, one violet accent,
# and semantic green/amber/red states. This makes the recording state carry the
# visual weight instead of a collection of competing colors.
ACCENT = "#8b5cf6"
ACCENT_HOVER = "#a78bfa"
ACCENT_MUTED = "#241b3d"
BG = "#09090b"
BG_ALT = "#0f0f12"
BG_CARD = "#18181b"
BG_ELEVATED = "#1f1f23"
BG_INPUT = "#09090b"
BORDER = "#27272a"
BORDER_SOFT = "#1f1f23"
TEXT = "#fafafa"
MUTED = "#a1a1aa"
DIMMED = "#71717a"
OK = "#22c55e"
WARN = "#f59e0b"
ERR = "#ef4444"
IDLE = "#71717a"

OK_BORDER, OK_BG = "#166534", "#0c2114"
REC_BORDER, REC_BG = "#991b1b", "#2a1012"
WARN_BORDER, WARN_BG = "#92400e", "#2a1b0b"
IDLE_BORDER, IDLE_BG = "#3f3f46", "#18181b"

QSS = f"""
QWidget {{
    font-size: 13px;
    color: {TEXT};
    font-family: "Segoe UI", "Inter", sans-serif;
}}
QMainWindow, QWidget#centralWidget {{ background: {BG}; }}

QLabel#pageTitle {{
    color: {TEXT}; font-size: 24px; font-weight: 700;
}}
QLabel#pageSubtitle, QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#dimmed {{ color: {DIMMED}; font-size: 11px; }}
QLabel#bigTimer {{
    color: {TEXT}; font-size: 42px; font-weight: 700;
    font-family: "Cascadia Code", "Consolas", monospace;
}}
QLabel#headerTitle {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#headerSubtitle {{ color: {DIMMED}; font-size: 11px; }}
QLabel#brandTitle {{ color: {TEXT}; font-size: 17px; font-weight: 700; }}
QLabel#brandSubtitle {{ color: {DIMMED}; font-size: 10px; }}
QLabel#sidebarHint {{ color: {DIMMED}; font-size: 10px; }}

QWidget#brandPanel {{
    background: {BG}; border-bottom: 1px solid {BORDER_SOFT};
}}
QWidget#sidebarFooter {{
    background: {BG}; border-top: 1px solid {BORDER_SOFT};
}}
QListWidget#sidebar {{
    background: {BG}; border: none; padding: 12px 10px;
    outline: none;
}}
QListWidget#sidebar::item {{
    color: {MUTED}; padding: 10px 13px; margin: 2px 0;
    border-radius: 7px; font-weight: 500;
}}
QListWidget#sidebar::item:hover {{
    background: #18181b; color: {TEXT};
}}
QListWidget#sidebar::item:selected {{
    background: {ACCENT_MUTED}; color: {TEXT};
    border: 1px solid #4c1d95; font-weight: 600;
}}

QPushButton {{
    background: {BG_CARD}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 7px; padding: 8px 14px; min-height: 18px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {BG_ELEVATED}; border-color: #52525b; }}
QPushButton:pressed {{ background: #27272a; }}
QPushButton:disabled {{
    color: #52525b; background: #111113; border-color: #1f1f23;
}}
QPushButton#primary {{
    background: {TEXT}; color: #09090b; border-color: {TEXT};
    font-weight: 650; padding: 10px 18px;
}}
QPushButton#primary:hover {{ background: #e4e4e7; border-color: #e4e4e7; }}
QPushButton#primary:disabled {{
    color: #71717a; background: #27272a; border-color: #27272a;
}}
QPushButton#danger {{
    background: #7f1d1d; color: #fecaca; border-color: #991b1b;
    font-weight: 650; padding: 10px 18px;
}}
QPushButton#danger:hover {{ background: #991b1b; color: white; }}
QPushButton#accent {{
    background: {ACCENT_MUTED}; color: #ddd6fe; border-color: #4c1d95;
}}
QPushButton#accent:hover {{ background: #35205c; border-color: {ACCENT}; }}
QPushButton#ghost {{
    background: transparent; border-color: transparent; color: {MUTED};
}}
QPushButton#ghost:hover {{ background: #18181b; color: {TEXT}; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_INPUT}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 7px; padding: 8px 10px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {BG_CARD}; color: {TEXT}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT_MUTED};
}}

QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    background: {BG_INPUT}; border: 1px solid {BORDER};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT_HOVER}; }}

QListWidget, QTreeWidget, QTableWidget {{
    background: {BG_ALT}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 9px; outline: none;
}}
QListWidget::item, QTreeWidget::item, QTableWidget::item {{
    padding: 7px 9px; border-radius: 5px;
}}
QListWidget::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{
    background: #1c1c20;
}}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {ACCENT_MUTED}; color: {TEXT};
}}
QHeaderView::section {{
    background: {BG_CARD}; color: {MUTED}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 9px 10px;
    font-size: 11px; font-weight: 650;
}}

QWidget#statusPill {{ border-radius: 12px; }}
QLabel#mono {{
    color: {MUTED}; font-size: 12px;
    font-family: "Cascadia Code", "Consolas", monospace;
}}
QWidget#targetCard, QWidget#captureModeCard, QWidget#adviceBox {{
    background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 10px;
}}
QWidget#captureModeCard {{ background: #12101a; border-color: #3b2a61; }}
QLabel#captureModeTitle {{ color: #ddd6fe; font-weight: 650; }}
QLabel#captureModeText {{ color: {MUTED}; font-size: 11px; }}
QLabel#preview {{
    background: #050506; color: {DIMMED}; border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#banner {{
    background: {REC_BG}; color: #fecaca; border: 1px solid {REC_BORDER};
    border-radius: 8px; padding: 10px 12px;
}}
QLabel#okBanner {{
    background: {OK_BG}; color: #bbf7d0; border: 1px solid {OK_BORDER};
    border-radius: 8px; padding: 10px 12px;
}}
QLabel#silenceBanner {{
    background: {WARN_BG}; color: #fde68a; border: 1px solid {WARN_BORDER};
    border-radius: 8px; padding: 9px 12px; font-weight: 600;
}}
QLabel#details {{
    background: {BG_CARD}; color: {MUTED}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 10px 12px;
}}
QLabel#tagProcess {{
    background: {ACCENT_MUTED}; color: #c4b5fd; border: 1px solid #4c1d95;
    border-radius: 5px; padding: 2px 7px; font-size: 11px; font-weight: 600;
}}
QLabel#tagHwnd {{
    background: {BG_INPUT}; color: {DIMMED}; border: 1px solid {BORDER};
    border-radius: 5px; padding: 2px 7px; font-size: 11px;
    font-family: "Cascadia Code", "Consolas", monospace;
}}
QLabel#tagClass {{ color: {DIMMED}; font-size: 11px; }}
QLabel#adviceText {{ color: #ddd6fe; font-size: 12px; font-weight: 500; }}

QGroupBox {{
    background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 9px;
    margin-top: 14px; padding: 15px 12px 10px 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 11px; padding: 0 5px;
    color: {MUTED}; font-size: 11px; font-weight: 650;
}}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3f3f46; min-height: 28px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: #52525b; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ background: {BG_ELEVATED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px 8px; }}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_ALT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_CARD))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_ELEVATED))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(DIMMED))
    disabled = QColor("#52525b")
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    app.setPalette(pal)
    app.setStyleSheet(QSS)
