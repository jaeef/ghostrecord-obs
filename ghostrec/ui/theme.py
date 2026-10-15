"""Dark theme for the GhostRec GUI (palette + light QSS)."""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

ACCENT = "#7c5cff"
BG = "#17181c"
BG_ALT = "#1f2127"
BORDER = "#34363d"
BORDER_SOFT = "#2a2c33"
TEXT = "#e8e9ee"
MUTED = "#9aa0a6"
OK = "#3fb950"
WARN = "#d29922"
ERR = "#f85149"
IDLE = "#6e7681"

QSS = f"""
QWidget {{ font-size: 13px; }}
QLabel#pageTitle {{ font-size: 17px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#bigTimer {{ font-size: 34px; font-weight: 700; }}
QLabel#banner {{
    background: #3a1d1d; border: 1px solid {ERR}; border-radius: 8px;
    padding: 10px 12px;
}}
QLabel#okBanner {{
    background: #17301c; border: 1px solid {OK}; border-radius: 8px;
    padding: 10px 12px;
}}
QLabel#preview {{
    background: #101114; border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    color: {MUTED};
}}
QLabel#details {{
    background: {BG_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    padding: 8px 10px;
}}
QPushButton {{
    background: {BG_ALT}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: #26272e; }}
QPushButton:disabled {{ color: #5c5f68; border-color: {BORDER_SOFT}; }}
QPushButton#primary {{
    background: {ACCENT}; border: 1px solid {ACCENT}; color: white;
    font-weight: 600; padding: 9px 20px;
}}
QPushButton#primary:hover {{ background: #8f73ff; }}
QPushButton#primary:disabled {{ background: #322e47; border-color: #322e47; color: #7a7890; }}
QPushButton#danger {{
    background: #8f2a2a; border: 1px solid #a83535; color: white;
    font-weight: 600; padding: 9px 20px;
}}
QPushButton#danger:hover {{ background: #a83535; }}
QPushButton#danger:disabled {{ background: #3a2424; border-color: #3a2424; color: #8a7070; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {BG_ALT}; border: 1px solid {BORDER}; border-radius: 6px;
    padding: 5px 8px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QListWidget, QTreeWidget, QTableWidget {{
    background: {BG_ALT}; border: 1px solid {BORDER_SOFT}; border-radius: 8px;
    outline: none;
}}
QListWidget#sidebar {{
    background: {BG}; border: none; border-radius: 0;
    padding: 8px 6px;
}}
QListWidget#sidebar::item {{ padding: 9px 12px; border-radius: 6px; color: {TEXT}; }}
QListWidget#sidebar::item:selected {{ background: #2b2840; color: white; }}
QListWidget::item, QTreeWidget::item, QTableWidget::item {{ padding: 4px 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background: {ACCENT}; color: white;
}}
QHeaderView::section {{
    background: {BG}; border: none; border-bottom: 1px solid {BORDER_SOFT};
    padding: 6px 8px; color: {MUTED};
}}
QGroupBox {{
    border: 1px solid {BORDER_SOFT}; border-radius: 8px; margin-top: 14px;
    padding: 10px 10px 6px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED};
}}
QCheckBox {{ spacing: 6px; }}
QSplitter::handle {{ background: {BORDER_SOFT}; }}
QToolTip {{
    background: {BG_ALT}; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px;
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
