"""Modal permission dialog presented when a tool needs user consent."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.permissions import (
    PermissionDecision,
    PermissionRequest,
)


class PermissionDialog(QDialog):
    """Asks the user to allow/deny a single tool action."""

    def __init__(
        self, request: PermissionRequest, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Permission Required")
        self.setModal(True)
        self.setMinimumWidth(560)

        self.request_obj = request
        self.decision: PermissionDecision = PermissionDecision.DENY

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Permission Required")
        title.setObjectName("Title")
        layout.addWidget(title)

        if request.dangerous:
            warn = QLabel("⚠️  Dangerous operation — this may be irreversible.")
            warn.setStyleSheet("color:#f87171;font-weight:600;")
            layout.addWidget(warn)

        body = QTextEdit()
        body.setReadOnly(True)
        body.setFrameShape(QTextEdit.NoFrame)
        body.setMinimumHeight(180)
        body.setHtml(self._render(request))
        layout.addWidget(body)

        buttons = QHBoxLayout()
        buttons.addStretch(1)

        deny = QPushButton("Deny")
        deny.setObjectName("Danger")
        deny.clicked.connect(self._deny)

        once = QPushButton("Allow Once")
        once.setObjectName("Primary")
        once.clicked.connect(self._allow_once)

        always = QPushButton("Always Allow")
        always.clicked.connect(self._always)
        always.setEnabled(not request.dangerous)

        buttons.addWidget(deny)
        buttons.addWidget(once)
        buttons.addWidget(always)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ #
    def _render(self, req: PermissionRequest) -> str:
        parts = [
            f"<b>Action:</b> {req.action.value}",
            f"<b>Target:</b> <code>{escape(req.target)}</code>",
        ]
        if req.reason:
            parts.append(f"<b>Why:</b> {escape(req.reason)}")
        if req.details:
            details = "<br>".join(
                f"&nbsp;&nbsp;<b>{escape(str(k))}:</b> {escape(str(v))}" for k, v in req.details.items()
            )
            parts.append(f"<b>Details:</b><br>{details}")
        return "<br><br>".join(parts)

    def _deny(self) -> None:
        self.decision = PermissionDecision.DENY
        self.accept()

    def _allow_once(self) -> None:
        self.decision = PermissionDecision.ALLOW_ONCE
        self.accept()

    def _always(self) -> None:
        self.decision = PermissionDecision.ALWAYS_ALLOW
        self.accept()
