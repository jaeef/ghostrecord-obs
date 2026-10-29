"""Dark theme for the GhostRec GUI (palette + light QSS)."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#bfe70e"
ACCENT_HOVER = "#c1e249a6"
ACCENT_MUTED = "#231e3d"
BG = "#090a0f"
BG_ALT = "#12141c"
BG_CARD = "#151824"
BG_INPUT = "#0d0f17"
BORDER = "#1f2230"
BORDER_SOFT = "#1f2230"
TEXT = "#f3f4f6"
MUTED = "#9ca3af"
DIMMED = "#64748b"
OK = "#10b981"
WARN = "#f59e0b"
ERR = "#ef4444"
IDLE = "#64748b"

# Status pill colors (border / background / dot) per the Obsidian spec
OK_BORDER, OK_BG = "#059669", "#0f281e"
REC_BORDER, REC_BG = "#dc2626", "#2b1416"
WARN_BORDER, WARN_BG = "#d97706", "#2d2010"
IDLE_BORDER, IDLE_BG = "#24283b", "#161924"

QSS = f"""
QWidget {{
    font-size: 13px;
    color: {TEXT};
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
}}
QLabel#pageTitle {{ font-size: 19px; font-weight: 700; color: #ffffff; letter-spacing: -0.2px; }}
QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QLabel#dimmed {{ color: {DIMMED}; font-size: 11px; }}
QLabel#bigTimer {{ font-size: 38px; font-weight: 800; font-family: "Cascadia Code", "Consolas", monospace; color: #ffffff; }}

QLabel#banner {{
    background: #2a1114; border: 1px solid #7f1d1d; border-radius: 8px;
    padding: 10px 14px; color: #fca5a5;
}}
QLabel#okBanner {{
    background: #0d281e; border: 1px solid #065f46; border-radius: 8px;
    padding: 10px 14px; color: #6ee7b7;
}}
QLabel#preview {{
    background: #0b0c12; border: 1px solid {BORDER_SOFT}; border-radius: 10px;
    color: {MUTED};
}}
QLabel#targetCard {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 10px;
}}
QLabel#tagProcess {{
    background: {ACCENT_MUTED}; color: #a78bfa; border: 1px solid #3d346b;
    border-radius: 4px; padding: 1px 7px; font-size: 11px; font-weight: 600;
}}
QLabel#tagHwnd {{
    background: {BG_INPUT}; color: {DIMMED}; border: 1px solid {BORDER};
    border-radius: 4px; padding: 1px 7px; font-size: 11px;
    font-family: "Cascadia Code", "Consolas", monospace;
}}
QLabel#tagClass {{
    color: {DIMMED}; font-size: 11px;
}}
QLabel#mono {{
    font-family: "Cascadia Code", "Consolas", monospace; color: {MUTED};
    font-size: 12px;
}}
QLabel#silenceBanner {{
    background: {WARN_BG}; border: 1px solid {WARN_BORDER}; border-radius: 8px;
    padding: 9px 14px; color: #fcd34d; font-weight: 600; font-size: 12px;
}}
QWidget#adviceBox {{
    background: {ACCENT_MUTED}; border: 1px solid #4c3aa0; border-radius: 8px;
}}
QLabel#adviceText {{
    color: #c4b5fd; font-size: 12px; font-weight: 500;
}}
QLabel#details {{
    background: {BG_CARD}; border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    padding: 9px 12px;
}}

QPushButton {{
    background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 7px 16px; font-weight: 500; color: {TEXT};
}}
QPushButton:hover {{
    background: #1c2030; border-color: {ACCENT}; color: #ffffff;
}}
QPushButton:pressed {{ background: #151824; }}
QPushButton:disabled {{ color: #4b5162; border-color: {BORDER_SOFT}; background: #10121a; }}

QPushButton#primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: #ffffff;
    font-weight: 600; padding: 9px 22px; border-radius: 6px;
}}
QPushButton#primary:hover {{
    background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER};
}}
QPushButton#primary:disabled {{
    background: #231e3b; border-color: #231e3b; color: #6b6687;
}}

QPushButton#danger {{
    background: #dc2626; border: 1px solid #ef4444; color: white;
    font-weight: 600; padding: 9px 22px; border-radius: 6px;
}}
QPushButton#danger:hover {{ background: #ef4444; }}
QPushButton#danger:disabled {{ background: #2f1717; border-color: #2f1717; color: #7f4b4b; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_INPUT}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 10px; selection-background-color: {ACCENT}; color: {TEXT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}

QListWidget, QTreeWidget, QTableWidget {{
    background: {BG_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 10px;
    outline: none;
}}
QListWidget#sidebar {{
    background: {BG}; border: none; border-right: 1px solid {BORDER_SOFT};
    padding: 12px 8px;
}}
QListWidget#sidebar::item {{
    padding: 10px 14px; border-radius: 8px; color: {MUTED}; font-weight: 500;
    margin-bottom: 4px;
}}
QListWidget#sidebar::item:hover {{
    background: #141724; color: {TEXT};
}}
QListWidget#sidebar::item:selected {{
    background: {ACCENT_MUTED}; color: #ffffff; font-weight: 600;
    border: 1px solid #3d346b;
}}

QListWidget::item, QTreeWidget::item, QTableWidget::item {{
    padding: 6px 8px; border-radius: 4px;
}}
QListWidget::item:hover, QTreeWidget::item:hover, QTableWidget::item:hover {{
    background: #1a1e2b;
}}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {ACCENT}; color: white;
}}

QHeaderView::section {{
    background: {BG}; border: none; border-bottom: 1px solid {BORDER_SOFT};
    padding: 8px 10px; color: {MUTED}; font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px;
}}

QScrollBar:vertical {{
    background: {BG_ALT}; width: 10px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #25293d; min-height: 24px; border-radius: 5px; margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {ACCENT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QGroupBox {{
    border: 1px solid {BORDER_SOFT}; border-radius: 8px; margin-top: 14px;
    padding: 12px 10px 8px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED};
    font-size: 12px; font-weight: 600;
}}
QPushButton#accent {{
    background: {ACCENT_MUTED}; border: 1px solid #4c3aa0; color: #c4b5fd;
    border-radius: 6px; padding: 6px 14px; font-weight: 600;
}}
QPushButton#accent:hover {{
    background: #35276b; border-color: {ACCENT}; color: #ffffff;
}}
QCheckBox {{ spacing: 8px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px;
    border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT}; border: 1px solid {ACCENT_HOVER};
}}
QSplitter::handle {{ background: {BORDER_SOFT}; }}
QToolTip {{
    background: {BG_CARD}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 6px 8px; border-radius: 4px;
}}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_ALT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_ALT))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_ALT))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(MUTED))
    disabled = QColor("#5c5f68")
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    app.setPalette(pal)
    app.setStyleSheet(QSS)
