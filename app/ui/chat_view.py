"""Chat area: scrollable message list with Markdown-ish rendering."""

from __future__ import annotations

import html
import re
from typing import Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication, QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

_CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)


def render_markdown(text: str) -> str:
    """Very small Markdown renderer: fenced code blocks, inline code, bold, headers."""
    if not text:
        return ""

    # Extract code blocks first so we don't touch them
    placeholders: list[tuple[str, str]] = []

    def _stash(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code = match.group(2)
        escaped = html.escape(code)
        label = f'<div style="color:#9aa0a6;font-size:11px;margin-bottom:4px;">{lang or "code"}</div>'
        block = (
            f'<div style="background:#111214;border:1px solid #2a2b2f;border-radius:6px;'
            f'padding:10px;margin:6px 0;">{label}'
            f'<pre style="margin:0;white-space:pre-wrap;font-family:Consolas,Menlo,monospace;'
            f'font-size:12px;color:#e6e6e6;">{escaped}</pre></div>'
        )
        token = f"@@CODEBLOCK_{len(placeholders)}@@"
        placeholders.append((token, block))
        return token

    body = _CODE_BLOCK_RE.sub(_stash, text)

    # Escape everything else
    body = html.escape(body)

    # Inline code
    body = re.sub(
        r"`([^`\n]+)`",
        r'<code style="background:#2a2b2f;padding:1px 5px;border-radius:4px;">\1</code>',
        body,
    )
    # Bold
    body = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", body)
    # Headers
    body = re.sub(
        r"^### (.+)$",
        r"<h4 style='margin:8px 0 4px 0;'>\1</h4>",
        body,
        flags=re.MULTILINE,
    )
    body = re.sub(
        r"^## (.+)$",
        r"<h3 style='margin:10px 0 4px 0;'>\1</h3>",
        body,
        flags=re.MULTILINE,
    )
    body = re.sub(
        r"^# (.+)$",
        r"<h2 style='margin:12px 0 6px 0;'>\1</h2>",
        body,
        flags=re.MULTILINE,
    )
    # Newlines
    body = body.replace("\n", "<br>")

    # Restore code blocks
    for token, block in placeholders:
        body = body.replace(token, block)

    return body


class MessageWidget(QFrame):
    """A single chat bubble."""

    def __init__(
        self, role: str, content: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.role = role
        self._content = content

        self.setFrameShape(QFrame.NoFrame)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        name = QLabel("You" if role == "user" else "DeepSeek Agent")
        name.setObjectName("Title")
        header.addWidget(name)
        header.addStretch(1)

        if role == "assistant":
            copy_btn = QPushButton("Copy")
            copy_btn.setFixedHeight(24)
            copy_btn.clicked.connect(self._copy)
            header.addWidget(copy_btn)

        layout.addLayout(header)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.NoFrame)
        self.browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.document().setDocumentMargin(0)
        font = QFont()
        font.setPointSize(10)
        self.browser.setFont(font)
        self.browser.setHtml(render_markdown(content))
        layout.addWidget(self.browser)

        self._autosize()

    # ------------------------------------------------------------------ #
    def append_text(self, delta: str) -> None:
        self._content += delta
        self.browser.setHtml(render_markdown(self._content))
        self._autosize()

    def set_content(self, content: str) -> None:
        self._content = content
        self.browser.setHtml(render_markdown(content))
        self._autosize()

    def _autosize(self) -> None:
        doc = self.browser.document()
        doc.setTextWidth(self.browser.viewport().width() or 600)
        height = int(doc.size().height()) + 8
        self.browser.setFixedHeight(max(24, height))
        self.updateGeometry()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._content)


class ChatView(QScrollArea):
    """Scrollable list of MessageWidget instances."""

    message_appended = Signal(str)  # role

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)
        self.setWidget(self._container)

        self._current: MessageWidget | None = None

    # ------------------------------------------------------------------ #
    def clear(self) -> None:
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._current = None

    def add_message(self, role: str, content: str = "") -> MessageWidget:
        widget = MessageWidget(role, content)
        self._layout.insertWidget(self._layout.count() - 1, widget)
        self._scroll_to_bottom()
        self.message_appended.emit(role)
        return widget

    def start_streaming(self, role: str = "assistant") -> MessageWidget:
        widget = self.add_message(role, "")
        self._current = widget
        return widget

    def append_stream(self, delta: str) -> None:
        if self._current is None:
            self._current = self.start_streaming()
        self._current.append_text(delta)
        self._scroll_to_bottom()

    def end_streaming(self) -> None:
        self._current = None

    def set_last_assistant(self, content: str) -> None:
        if self._current is not None:
            self._current.set_content(content)

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, MessageWidget):
                w._autosize()  # noqa: SLF001
