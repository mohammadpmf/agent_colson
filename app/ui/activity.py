"""Right sidebar: live agent activity stream."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ActivityPanel(QFrame):
    """Append-only log of tool calls, plans, and state changes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Activity")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        title = QLabel("AGENT ACTIVITY")
        title.setObjectName("Sub")
        layout.addWidget(title)

        self.list = QListWidget()
        self.list.setWordWrap(True)
        layout.addWidget(self.list, stretch=1)

    def add(self, text: str, icon: str = "•") -> None:
        item = QListWidgetItem(f"{icon} {text}")
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list.addItem(item)
        self.list.scrollToBottom()

    def clear(self) -> None:
        self.list.clear()
