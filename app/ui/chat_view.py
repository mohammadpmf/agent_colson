"""Chat area: scrollable message list with Markdown-ish rendering."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
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

# Unicode ranges that count as "strong RTL" for direction detection.
_RTL_CHARS = re.compile(
    "[\u0590-\u05ff"  # Hebrew
    "\u0600-\u06ff"  # Arabic
    "\u0700-\u074f"  # Syriac
    "\u0750-\u077f"  # Arabic Supplement
    "\u0780-\u07bf"  # Thaana
    "\u08a0-\u08ff"  # Arabic Extended-A
    "\ufb1d-\ufdff"  # Hebrew + Arabic presentation
    "\ufe70-\ufeff"  # Arabic presentation forms B
    "\U00010800-\U00010fff"  # various historic scripts
    "\U0001e900-\U0001e95f"  # Adlam
    "]"
)

# "strong LTR" = letters from Latin/Greek/Cyrillic blocks.
_LTR_CHARS = re.compile(
    "[A-Za-z"
    "\u00c0-\u024f"  # Latin extended
    "\u0370-\u03ff"  # Greek
    "\u0400-\u04ff"  # Cyrillic
    "\u1e00-\u1eff"  # Latin extended additional
    "]"
)


def _line_direction(line: str) -> str:
    """Return 'rtl', 'ltr', or 'neutral' for a single line of text."""
    rtl = bool(_RTL_CHARS.search(line))
    ltr = bool(_LTR_CHARS.search(line))
    if rtl and ltr:
        return "mixed"
    if rtl:
        return "rtl"
    if ltr:
        return "ltr"
    return "neutral"


def _isolate_ltr_runs(text: str) -> str:
    """Inside a mixed RTL line, wrap Latin runs in <span dir="ltr">.

    This lets the outer RTL paragraph keep its right-to-left base direction
    while Latin segments (like 'How can I assist you today?') render as
    proper LTR islands with the punctuation on their right side.
    """
    # A "Latin run" = one or more chars from the Latin/Greek/Cyrillic ranges,
    # optionally including the punctuation that commonly attaches to them.
    pattern = re.compile(
        r"([A-Za-z\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u1E00-\u1EFF"
        r"0-9][A-Za-z0-9\u00C0-\u024F\u0370-\u03FF\u0400-\u04FF\u1E00-\u1EFF\s\.\,\!\?\'\"\-\_\:\;\(\)\[\]\/\@\#\$\%\&\*\+\=]*)"
    )

    def _wrap(m: re.Match) -> str:
        run = m.group(1).strip()
        if not run:
            return m.group(1)
        return f'<span dir="ltr" style="unicode-bidi:embed;">{html.escape(run)}</span>'

    return pattern.sub(_wrap, text)


def render_markdown(text: str) -> str:
    """Small Markdown renderer.

    Direction strategy — one <p> per source line, with an explicit dir
    attribute. Qt supports `<p dir="rtl|ltr">` and `<span dir="...">`
    reliably, but does *not* support CSS `unicode-bidi: plaintext`, so
    we must set direction ourselves line by line.
    """
    if not text:
        return ""

    # --- 1) Extract fenced code blocks so their content is untouched -----
    placeholders: list[tuple[str, str]] = []

    def _stash(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code = match.group(2)
        escaped = html.escape(code)
        label = (
            f'<div dir="ltr" style="color:#9aa0a6;font-size:11px;'
            f'margin-bottom:4px;text-align:left;">{html.escape(lang or "code")}</div>'
        )
        block = (
            f'<div dir="ltr" style="background:#111214;border:1px solid #2a2b2f;'
            f'border-radius:6px;padding:10px;margin:6px 0;text-align:left;">'
            f"{label}"
            f'<pre style="margin:0;white-space:pre-wrap;'
            f'font-family:Consolas,Menlo,monospace;font-size:12px;color:#e6e6e6;">'
            f"{escaped}</pre></div>"
        )
        token = f"@@CODEBLOCK_{len(placeholders)}@@"
        placeholders.append((token, block))
        return token

    body = _CODE_BLOCK_RE.sub(_stash, text)

    # --- 2) Escape everything, then apply inline markdown ---------------
    body = html.escape(body)

    # Inline code -> LTR inline span
    body = re.sub(
        r"`([^`\n]+)`",
        r'<span dir="ltr" style="background:#2a2b2f;padding:1px 5px;'
        r'border-radius:4px;font-family:Consolas,Menlo,monospace;">\1</span>',
        body,
    )

    # Bold
    body = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", body)

    # --- 3) Restore code-block placeholders before line splitting -------
    # We use a sentinel that survives the line loop without containing \n.
    # Each placeholder already has its own <div>, so we can treat it as its
    # own "line" during rendering.
    CODE_TOKEN_SENTINEL = "\ue000"  # private-use area, won't appear in text
    for i, (token, block) in enumerate(placeholders):
        body = body.replace(token, f"{CODE_TOKEN_SENTINEL}{i}{CODE_TOKEN_SENTINEL}")

    # --- 4) Split into lines and render each as its own <p> -------------
    raw_lines = body.split("\n")
    out_parts: list[str] = []

    for line in raw_lines:
        stripped = line.rstrip()

        # Handle code-block sentinels on their own line
        if CODE_TOKEN_SENTINEL in stripped:
            # Replace each sentinel with its block; keep the rest of the line
            def _restore(m: re.Match) -> str:
                idx = int(m.group(1))
                return placeholders[idx][1]

            line = re.sub(
                f"{CODE_TOKEN_SENTINEL}(\\d+){CODE_TOKEN_SENTINEL}",
                _restore,
                stripped,
            )
            out_parts.append(line)
            continue

        if not stripped:
            # Preserve blank lines as a thin spacer paragraph.
            out_parts.append(
                '<p style="margin:0;height:6px;line-height:6px;">&nbsp;</p>'
            )
            continue

        direction = _line_direction(stripped)

        if direction == "rtl":
            out_parts.append(f'<p dir="rtl" style="margin:2px 0;">{stripped}</p>')
        elif direction == "ltr":
            out_parts.append(f'<p dir="ltr" style="margin:2px 0;">{stripped}</p>')
        elif direction == "mixed":
            # Base direction = rtl (persian mixed with english is common).
            # Isolate Latin runs so they keep their own direction.
            isolated = _isolate_ltr_runs(stripped)
            out_parts.append(f'<p dir="rtl" style="margin:2px 0;">{isolated}</p>')
        else:
            # Neutral line (numbers, punctuation only).
            out_parts.append(f'<p dir="auto" style="margin:2px 0;">{stripped}</p>')

    return "".join(out_parts)


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
        doc.adjustSize()
        height = int(doc.size().height()) + 16
        height = max(height, 44)
        self.browser.setFixedHeight(height)
        self.updateGeometry()

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
        self._current.append_text(delta)
        self._scroll_to_bottom()

    def end_streaming(self) -> None:
        self._current = None

    def has_active_stream(self) -> bool:
        return self._current is not None

    def finalize_stream(self, content: str) -> None:
        if self._current is not None:
            self._current.set_content(content)
        self._current = None

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        for i in range(self._layout.count()):
            w = self._layout.itemAt(i).widget()
            if isinstance(w, MessageWidget):
                w._autosize()  # noqa: SLF001
