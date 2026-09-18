"""Chat area: scrollable message list with Markdown-ish rendering."""

from __future__ import annotations

import html
import re
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QGuiApplication, QTextOption
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

from xml.etree import ElementTree as ET
from urllib.parse import urlsplit

import markdown

from .text_direction import text_direction


def render_markdown(text: str) -> str:
    """Render Markdown without interpreting user HTML; direct each block separately."""
    md = markdown.Markdown(extensions=["fenced_code", "tables", "nl2br"])
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    rendered = md.convert(text)
    rendered = re.sub(r"&([A-Za-z][A-Za-z0-9]+);", lambda match: (
        "&#" + str(html.entities.name2codepoint[match[1]]) + ";"
        if match[1] in html.entities.name2codepoint else match[0]
    ), rendered)
    try:
        root = ET.fromstring("<div>" + rendered + "</div>")
    except ET.ParseError:
        direction = text_direction(text)
        alignment = "right" if direction == "rtl" else "left"
        return f'<p dir="{direction}" align="{alignment}">{html.escape(text).replace(chr(10), "<br>")}</p>'
    for node in root.iter():
        if node.tag in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote", "pre"}:
            direction = "ltr" if node.tag == "pre" else text_direction("".join(node.itertext()))
            node.set("dir", direction)
            node.set("align", "right" if direction == "rtl" else "left")
        if node.tag in {"pre", "code"}:
            node.set("dir", "ltr")
            node.set("style", "font-family:Consolas,monospace;")
        if node.tag == "a" and urlsplit(node.get("href", "")).scheme not in {"http", "https", "mailto"}:
            node.attrib.pop("href", None)
        if node.tag == "img":
            node.tag = "span"
            node.text = node.get("alt", "")
            node.attrib.clear()
    return ET.tostring(root, encoding="unicode", method="html")


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
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.setContentsMargins(0, 0, 0, 0)

        name = QLabel("You" if role == "user" else "Assistant")
        name.setObjectName("Title")
        header.addWidget(name, alignment=Qt.AlignVCenter)
        header.addStretch(1)

        if role == "assistant":
            copy_btn = QPushButton("Copy")
            copy_btn.setObjectName("CopyButton")
            copy_btn.setMinimumHeight(32)
            copy_btn.setMinimumWidth(72)
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.clicked.connect(self._copy)
            header.addWidget(copy_btn, alignment=Qt.AlignVCenter)

        layout.addLayout(header)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.NoFrame)
        self.browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.document().setDocumentMargin(0)
        self.browser.setStyleSheet("QTextBrowser { background: transparent; }")
        font = QFont()
        font.setPointSize(10)
        self.browser.setFont(font)
        self.browser.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
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
        width = self.browser.viewport().width()
        if width <= 0:
            width = 600
        doc.setTextWidth(width)
        height = int(doc.size().height()) + 16
        height = max(height, 44)
        self.browser.setFixedHeight(height)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._autosize)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._content)


class ChatView(QScrollArea):
    """Scrollable list of MessageWidget instances."""

    message_appended = Signal(str)

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
        bar = self.verticalScrollBar()
        follow = bar.maximum() - bar.value() < 40
        self._current.append_text(delta)
        if follow:
            self._scroll_to_bottom()

    def end_streaming(self) -> str:
        content = self._current._content if self._current is not None else ""
        self._current = None
        return content

    def has_active_stream(self) -> bool:
        return self._current is not None

    def finalize_stream(self, content: str) -> None:
        if self._current is not None:
            self._current.set_content(content)
        self._current = None

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
        QTimer.singleShot(0, lambda: bar.setValue(bar.maximum()))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, MessageWidget):
                w._autosize()  # noqa: SLF001
