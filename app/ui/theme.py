"""Dark / light stylesheets for the application."""

from __future__ import annotations

DARK_QSS = """
* { font-family: 'Segoe UI', 'Inter', 'SF Pro Text', sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #1e1f22; color: #e6e6e6; }
QFrame#Sidebar, QFrame#Activity { background: #17181a; border: none; }
QFrame#TopBar { background: #17181a; border-bottom: 1px solid #2a2b2f; }
QFrame#Composer { background: #17181a; border-top: 1px solid #2a2b2f; }
QLabel#Title { font-size: 14px; font-weight: 600; color: #f5f5f5; }
QLabel#Sub { color: #9aa0a6; font-size: 12px; }
QLabel#StatusOk { color: #4ade80; font-weight: 600; }
QLabel#StatusBad { color: #f87171; font-weight: 600; }
QPushButton {
    background: #2a2b2f; color: #e6e6e6; border: 1px solid #35363a;
    border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover { background: #35363a; }
QPushButton:pressed { background: #404146; }
QPushButton#Primary { background: #2563eb; border-color: #2563eb; color: white; font-weight: 600; }
QPushButton#Primary:hover { background: #1d4ed8; }
QPushButton#Danger { background: #7f1d1d; border-color: #991b1b; color: #fee2e2; }
QPushButton#Danger:hover { background: #991b1b; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #202124; color: #e6e6e6; border: 1px solid #35363a; border-radius: 6px; padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #2563eb; }
QListWidget, QTreeWidget {
    background: #17181a; color: #e6e6e6; border: none; outline: none;
}
QListWidget::item:selected, QTreeWidget::item:selected { background: #2a2b2f; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #232427; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a3b40; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #4a4b51; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QTabWidget::pane { border: 1px solid #2a2b2f; border-radius: 6px; }
QTabBar::tab { background: #202124; color: #c0c0c0; padding: 6px 14px; }
QTabBar::tab:selected { background: #2a2b2f; color: white; }
QMenuBar { background: #17181a; }
QMenu { background: #202124; color: #e6e6e6; border: 1px solid #35363a; }
QMenu::item:selected { background: #2a2b2f; }
QGroupBox { border: 1px solid #2a2b2f; border-radius: 6px; margin-top: 10px; padding-top: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #9aa0a6; }
"""


LIGHT_QSS = """
* { font-family: 'Segoe UI', 'Inter', 'SF Pro Text', sans-serif; font-size: 13px; }
QMainWindow, QWidget { background: #f7f7f8; color: #202124; }
QFrame#Sidebar, QFrame#Activity { background: #efeff1; border: none; }
QFrame#TopBar { background: #ffffff; border-bottom: 1px solid #e0e0e3; }
QFrame#Composer { background: #ffffff; border-top: 1px solid #e0e0e3; }
QLabel#Title { font-size: 14px; font-weight: 600; }
QLabel#Sub { color: #5f6368; font-size: 12px; }
QLabel#StatusOk { color: #16a34a; font-weight: 600; }
QLabel#StatusBad { color: #dc2626; font-weight: 600; }
QPushButton {
    background: #ffffff; color: #202124; border: 1px solid #d5d5d8;
    border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover { background: #f0f0f3; }
QPushButton#Primary { background: #2563eb; border-color: #2563eb; color: white; font-weight: 600; }
QPushButton#Primary:hover { background: #1d4ed8; }
QPushButton#Danger { background: #dc2626; border-color: #dc2626; color: white; }
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff; color: #202124; border: 1px solid #d5d5d8; border-radius: 6px; padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color: #2563eb; }
QListWidget, QTreeWidget { background: #ffffff; color: #202124; border: none; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #e0e8ff; color: #111827; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #f0f0f3; }
"""


def stylesheet(name: str) -> str:
    return DARK_QSS if name == "dark" else LIGHT_QSS
