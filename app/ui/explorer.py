"""Left sidebar: workspace file tree + recent chats."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.workspace import WorkspaceManager


class ExplorerPanel(QFrame):
    """Shows the workspace tree and lets the user open files."""

    file_selected = Signal(str)  # absolute path
    open_workspace_requested = Signal()

    def __init__(
        self, workspace: WorkspaceManager, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(280)
        self.workspace = workspace

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("PROJECT")
        title.setObjectName("Sub")
        header.addWidget(title)
        header.addStretch(1)
        open_btn = QPushButton("Open")
        open_btn.setFixedHeight(24)
        open_btn.clicked.connect(self.open_workspace_requested.emit)
        header.addWidget(open_btn)
        layout.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        self.tree.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self.tree, stretch=3)

        # Recent chats
        recent_label = QLabel("RECENT CHATS")
        recent_label.setObjectName("Sub")
        layout.addWidget(recent_label)

        self.recent = QListWidget()
        self.recent.setMaximumHeight(180)
        layout.addWidget(self.recent, stretch=1)

    # ------------------------------------------------------------------ #
    def refresh(self) -> None:
        self.tree.clear()
        if self.workspace.root is None:
            return
        self.tree.addTopLevelItem(self._build(self.workspace.root))
        self.tree.expandToDepth(1)

    def set_recent_chats(self, items: list[tuple[str, str]]) -> None:
        """items: list of (conversation_id, title)."""
        self.recent.clear()
        for conv_id, title in items:
            item = QListWidgetItem(title or "(untitled)")
            item.setData(Qt.UserRole, conv_id)
            self.recent.addItem(item)

    def _build(self, path: Path) -> QTreeWidgetItem:
        item = QTreeWidgetItem([path.name or str(path)])
        item.setData(0, Qt.UserRole, str(path))
        try:
            children = sorted(
                (
                    p
                    for p in path.iterdir()
                    if p.name
                    not in {
                        ".git",
                        "__pycache__",
                        "node_modules",
                        ".venv",
                        "venv",
                        ".idea",
                        ".vscode",
                        ".pytest_cache",
                        "dist",
                        "build",
                    }
                ),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except (OSError, PermissionError):
            return item
        for child in children:
            if child.is_dir():
                item.addChild(self._build(child))
            else:
                leaf = QTreeWidgetItem([child.name])
                leaf.setData(0, Qt.UserRole, str(child))
                item.addChild(leaf)
        return item

    def _on_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        path = item.data(0, Qt.UserRole)
        if not path:
            return
        p = Path(path)
        if p.is_file():
            self.file_selected.emit(str(p))
