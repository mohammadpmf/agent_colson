"""Main application window wiring everything together."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QEventLoop
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.agent import AgentEngine, AgentEvent, AgentEventType, AgentMode, AgentState
from app.config import AppConfig
from app.context import ContextManager
from app.conversations import Conversation, ConversationStore, StoredMessage
from app.permissions import (
    PermissionDecision,
    PermissionManager,
    PermissionRequest,
)
from app.permissions.storage import PermissionStorage
from app.providers import (
    ChatMessage,
    DeepSeekProvider,
    GapGPTProvider,
    LLMProvider,
    ToolCall,
)
from app.tools import ToolContext, build_default_registry
from app.workspace import WorkspaceManager

from .activity import ActivityPanel
from .chat_view import ChatView
from .explorer import ExplorerPanel
from .permission_dialog import PermissionDialog
from .settings_dialog import SettingsDialog
from .theme import stylesheet
from .workers import run_in_thread

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window: sidebar, chat, activity panel, composer."""

    _permission_requested = Signal(object, object)
    _agent_event = Signal(object)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("Local Coding Agent")
        self.resize(1400, 900)

        self._agent_event.connect(self._apply_agent_event)

        # ---- core services ------------------------------------------------
        self.workspace = WorkspaceManager()
        if config.workspace:
            try:
                self.workspace.set_root(config.workspace)
            except (FileNotFoundError, NotADirectoryError):
                pass

        self.permission_storage = PermissionStorage(config.data_dir / "agent.db")
        self.permissions = PermissionManager(
            self.permission_storage,
            self.workspace.root or config.data_dir,
            ask_callback=self._ask_permission,
        )
        self.registry = build_default_registry()
        self.conversation_store = ConversationStore(config.data_dir / "conversations")

        self.conversation = Conversation(
            workspace=str(self.workspace.root or ""),
            model=config.model,
        )
        self.agent: AgentEngine | None = None

        self._conn_thread = None
        self._conn_worker = None

        # ---- UI -----------------------------------------------------------
        self._build_ui()
        self._apply_theme(config.theme)
        self._build_menus()
        self._wire_shortcuts()
        self._refresh_recent_chats()
        self._update_workspace_label()

        QTimer.singleShot(100, self._refresh_connection_status)

        if not self.workspace.root:
            QTimer.singleShot(400, self._prompt_first_run)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_top_bar())

        splitter = QSplitter(Qt.Horizontal)
        self.explorer = ExplorerPanel(self.workspace)
        self.explorer.file_selected.connect(self._on_file_selected)
        self.explorer.open_workspace_requested.connect(self._choose_workspace)
        splitter.addWidget(self.explorer)

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)
        self.chat = ChatView()
        chat_layout.addWidget(self.chat, stretch=1)
        chat_layout.addWidget(self._build_composer())
        splitter.addWidget(chat_container)

        self.activity = ActivityPanel()
        splitter.addWidget(self.activity)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 820, 300])
        outer.addWidget(splitter, stretch=1)

        outer.addWidget(self._build_status_bar())

    def _build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        title = QLabel("Local Coding Agent")
        title.setObjectName("Title")
        layout.addWidget(title)

        self.conn_status = QLabel("●")
        self.conn_status.setObjectName("StatusBad")
        layout.addWidget(self.conn_status)

        self.provider_label = QLabel(f"({self.config.provider})")
        self.provider_label.setObjectName("Sub")
        layout.addWidget(self.provider_label)

        self.workspace_label = QLabel("Workspace: (none)")
        self.workspace_label.setObjectName("Sub")
        layout.addWidget(self.workspace_label)

        layout.addStretch(1)

        layout.addWidget(QLabel("Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Agent", "Ask"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        new_chat_btn = QPushButton("New Chat")
        new_chat_btn.clicked.connect(self._new_chat)
        layout.addWidget(new_chat_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(settings_btn)

        return bar

    def _build_composer(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Composer")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self.input = QTextEdit()
        self.input.setPlaceholderText(
            "Ask the agent to inspect, modify, or run something… (Ctrl+Enter to send)"
        )
        self.input.setFixedHeight(84)
        layout.addWidget(self.input, stretch=1)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("Primary")
        send_btn.setFixedWidth(96)
        send_btn.clicked.connect(self._send)
        layout.addWidget(send_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setFixedWidth(96)
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)

        return frame

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setFixedHeight(28)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)

        self.status_left = QLabel("Ready")
        self.status_left.setObjectName("Sub")
        layout.addWidget(self.status_left)

        layout.addStretch(1)
        self.token_label = QLabel("tokens: 0 in / 0 out")
        self.token_label.setObjectName("Sub")
        layout.addWidget(self.token_label)

        return bar

    def _build_menus(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&File")

        new_action = QAction("&New Chat", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._new_chat)
        file_menu.addAction(new_action)

        open_action = QAction("&Open Workspace…", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._choose_workspace)
        file_menu.addAction(open_action)

        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menu.addMenu("&Help")
        about = QAction("&About", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    def _wire_shortcuts(self) -> None:
        send = QAction(self)
        send.setShortcut(QKeySequence("Ctrl+Return"))
        send.triggered.connect(self._send)
        self.addAction(send)

        send2 = QAction(self)
        send2.setShortcut(QKeySequence("Ctrl+Enter"))
        send2.triggered.connect(self._send)
        self.addAction(send2)

        stop = QAction(self)
        stop.setShortcut(QKeySequence("Esc"))
        stop.triggered.connect(self._stop)
        self.addAction(stop)

        focus = QAction(self)
        focus.setShortcut(QKeySequence("Ctrl+L"))
        focus.triggered.connect(lambda: self.input.setFocus())
        self.addAction(focus)

    # ------------------------------------------------------------------ #
    # Theme / status
    # ------------------------------------------------------------------ #
    def _apply_theme(self, name: str) -> None:
        self.setStyleSheet(stylesheet(name))

    def _refresh_connection_status(self) -> None:
        if not self.config.api_key:
            self.conn_status.setText("● not configured")
            self.conn_status.setObjectName("StatusBad")
            self._restyle(self.conn_status)
            self._set_status(
                f"No API key configured for {self.config.provider}. "
                f"Open Settings → {self.config.provider.title()}."
            )
            return

        self.conn_status.setText("● testing…")
        self.conn_status.setObjectName("StatusBad")
        self._restyle(self.conn_status)

        provider_name = self.config.provider
        api_key = self.config.api_key
        base_url = self.config.base_url
        model = self.config.model

        def _test() -> tuple[bool, str]:
            if provider_name == "gapgpt":
                p = GapGPTProvider(
                    api_key=api_key, model=model, base_url=base_url, timeout=20
                )
            else:
                p = DeepSeekProvider(
                    api_key=api_key, model=model, base_url=base_url, timeout=20
                )
            return p.test_connection()

        thread, worker = run_in_thread(self, _test)

        def _on_done(result) -> None:
            ok, msg = result
            if ok:
                self.conn_status.setText("● connected")
                self.conn_status.setObjectName("StatusOk")
                self.activity.add(f"{provider_name}: {msg}", "✓")
            else:
                self.conn_status.setText("● offline")
                self.conn_status.setObjectName("StatusBad")
                self.activity.add(f"{provider_name}: {msg}", "!")
                QMessageBox.warning(
                    self,
                    f"{provider_name} connection failed",
                    f"{msg}\n\nCheck your API key in Settings → {provider_name.title()}.",
                )
            self._restyle(self.conn_status)

        def _on_fail(err: str) -> None:
            self.conn_status.setText("● error")
            self.conn_status.setObjectName("StatusBad")
            self._restyle(self.conn_status)
            self.activity.add(f"{provider_name} test failed: {err}", "!")

        worker.finished.connect(_on_done)
        worker.failed.connect(_on_fail)
        self._conn_thread = thread
        self._conn_worker = worker

    def _restyle(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _set_status(self, text: str) -> None:
        self.status_left.setText(text)

    def _set_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self.token_label.setText(f"tokens: {input_tokens:,} in / {output_tokens:,} out")

    def _update_workspace_label(self) -> None:
        if self.workspace.root:
            self.workspace_label.setText(f"Workspace: {self.workspace.root.name}")
        else:
            self.workspace_label.setText("Workspace: (none)")

    def _update_provider_label(self) -> None:
        self.provider_label.setText(f"({self.config.provider})")

    # ------------------------------------------------------------------ #
    # Workspace
    # ------------------------------------------------------------------ #
    def _choose_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose Workspace Folder")
        if not path:
            return
        try:
            self.workspace.set_root(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Invalid workspace", str(exc))
            return
        self.config.workspace = str(self.workspace.root)
        self.config.add_recent_workspace(str(self.workspace.root))
        self.config.save()
        self.permissions.set_workspace(self.workspace.root)
        self._update_workspace_label()
        self.explorer.refresh()
        self.conversation.workspace = str(self.workspace.root)
        self._set_status(f"Workspace: {self.workspace.root}")

    def _on_file_selected(self, path: str) -> None:
        try:
            self.workspace.resolve(path)
        except Exception:  # noqa: BLE001
            return
        rel = Path(path).name
        self.input.insertPlainText(f"Please read `{rel}` and explain its purpose.\n")

    # ------------------------------------------------------------------ #
    # Conversation
    # ------------------------------------------------------------------ #
    def _new_chat(self) -> None:
        if self.conversation.messages:
            self.conversation_store.save(self.conversation)
        self.conversation = Conversation(
            workspace=str(self.workspace.root or ""),
            model=self.config.model,
        )
        self.chat.clear()
        self.activity.clear()
        self._set_tokens(0, 0)
        self._set_status("New chat started.")
        self._refresh_recent_chats()

    def _refresh_recent_chats(self) -> None:
        items = [(c.id, c.title) for c in self.conversation_store.list_all()]
        self.explorer.set_recent_chats(items)

    # ------------------------------------------------------------------ #
    # Agent
    # ------------------------------------------------------------------ #
    def _on_mode_changed(self, text: str) -> None:
        self._set_status(f"Mode: {text}")

    def _current_mode(self) -> AgentMode:
        return (
            AgentMode.AGENT
            if self.mode_combo.currentText() == "Agent"
            else AgentMode.ASK
        )

    def _send(self) -> None:
        if self.agent and self.agent.is_running:
            return
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self.workspace.root is None:
            QMessageBox.warning(self, "No workspace", "Please open a workspace first.")
            return
        if not self.config.api_key:
            QMessageBox.warning(
                self,
                "API key missing",
                f"Please enter your {self.config.provider} API key in Settings.",
            )
            return

        self.input.clear()
        self.chat.add_message("user", text)
        self.conversation.messages.append(StoredMessage(role="user", content=text))
        if len(self.conversation.messages) == 1:
            self.conversation.title = text[:60]

        history = self._build_api_history(exclude_last=True)

        provider = self._make_provider()
        tool_ctx = ToolContext(workspace=self.workspace, permissions=self.permissions)

        self.agent = AgentEngine(
            provider=provider,
            registry=self.registry,
            tool_context=tool_ctx,
            mode=self._current_mode(),
            emit=self._handle_agent_event,
            context_manager=ContextManager(
                max_tokens=12_000,
                keep_last=8,
                max_tool_result_chars=2_000,
            ),
        )
        self.stop_btn.setEnabled(True)
        self._set_status("Agent running…")
        self.activity.add("Planning…", "⟳")
        self.agent.start(history=history, user_input=text)

    def _build_api_history(self, exclude_last: bool = False) -> list[ChatMessage]:
        """Convert stored messages into provider ChatMessages.

        Every `assistant` message that carries tool_calls is followed by one
        `tool` message per call — the pairing OpenAI-compatible backends
        require.
        """
        stored = self.conversation.messages
        if exclude_last and stored and stored[-1].role == "user":
            stored = stored[:-1]

        history: list[ChatMessage] = []
        for m in stored:
            if m.role == "user":
                history.append(ChatMessage(role="user", content=m.content))
                continue

            if m.role == "assistant":
                if m.tool_calls:
                    tcs: list[ToolCall] = []
                    for tc in m.tool_calls:
                        fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                        try:
                            args = json.loads(fn.get("arguments", "{}") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        tcs.append(
                            ToolCall(
                                id=tc.get("id", ""),
                                name=fn.get("name", ""),
                                arguments=args,
                            )
                        )
                    history.append(
                        ChatMessage(
                            role="assistant",
                            content="",
                            tool_calls=tcs,
                        )
                    )
                else:
                    history.append(ChatMessage(role="assistant", content=m.content))
                continue

            if m.role == "tool":
                history.append(
                    ChatMessage(
                        role="tool",
                        content=m.content,
                        tool_call_id=m.tool_call_id,
                        name=m.tool_name,
                    )
                )
        return history

    def _stop(self) -> None:
        if self.agent and self.agent.is_running:
            self.agent.cancel()
            self.activity.add("Cancellation requested", "■")
            self._set_status("Cancelling…")

    def _make_provider(self) -> LLMProvider:
        if self.config.provider == "gapgpt":
            return GapGPTProvider(
                api_key=self.config.gapgpt_api_key,
                model=self.config.gapgpt_model,
                base_url=self.config.gapgpt_base_url,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        return DeepSeekProvider(
            api_key=self.config.deepseek_api_key,
            model=self.config.deepseek_model,
            base_url=self.config.deepseek_base_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    # ------------------------------------------------------------------ #
    # Agent events
    # ------------------------------------------------------------------ #
    def _handle_agent_event(self, event: AgentEvent) -> None:
        self._agent_event.emit(event)

    def _apply_agent_event(self, event: AgentEvent) -> None:
        if event.type == AgentEventType.STATE:
            self._on_state(event.payload.get("state", ""))

        elif event.type == AgentEventType.ASSISTANT_TOKEN:
            self.chat.append_stream(event.payload.get("delta", ""))

        elif event.type == AgentEventType.ASSISTANT_MESSAGE:
            content = event.payload.get("content", "")
            if not content:
                return
            if self.chat.has_active_stream():
                self.chat.finalize_stream(content)
            else:
                self.chat.add_message("assistant", content)
            self.conversation.messages.append(
                StoredMessage(role="assistant", content=content)
            )

        elif event.type == AgentEventType.TOOL_CALL:
            name = event.payload.get("name", "")
            args = event.payload.get("arguments", {})
            call_id = event.payload.get("id", "")
            summary = _summarize_tool_call(name, args)
            self.activity.add(f"{name}: {summary}", "▶")

            # Persist the assistant tool-call message so the matching tool
            # result has a proper parent when the history is rebuilt.
            self.conversation.messages.append(
                StoredMessage(
                    role="assistant",
                    content="",
                    tool_calls=[
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(args, ensure_ascii=False),
                            },
                        }
                    ],
                )
            )

        elif event.type == AgentEventType.TOOL_RESULT:
            name = event.payload.get("name", "")
            ok = event.payload.get("ok", False)
            output = event.payload.get("output", "")
            call_id = event.payload.get("id", "")
            icon = "✓" if ok else "✗"
            self.activity.add(f"{name} → {icon}", icon)
            self.conversation.messages.append(
                StoredMessage(
                    role="tool",
                    content=output,
                    tool_call_id=call_id,
                    tool_name=name,
                )
            )

        elif event.type == AgentEventType.ERROR:
            msg = event.payload.get("message", "Unknown error")
            self.activity.add(msg, "!")
            self.chat.end_streaming()
            self.chat.add_message("assistant", f"⚠️ Error: {msg}")

        elif event.type == AgentEventType.USAGE:
            self._set_tokens(
                int(event.payload.get("input", 0)),
                int(event.payload.get("output", 0)),
            )

        elif event.type == AgentEventType.DONE:
            self.chat.end_streaming()
            state = event.payload.get("state", "completed")
            self._set_status(f"Agent: {state}")
            self.stop_btn.setEnabled(False)
            self.conversation.updated_at = time.time()
            self.conversation_store.save(self.conversation)
            self._refresh_recent_chats()
            self._update_workspace_label()

    def _on_state(self, state: str) -> None:
        mapping = {
            "idle": "Idle",
            "planning": "Planning…",
            "waiting_for_api": "Waiting for API…",
            "running": "Running…",
            "waiting_for_permission": "Waiting for permission…",
            "completed": "Done",
            "failed": "Failed",
            "canceled": "Canceled",
        }
        self._set_status(f"Agent: {mapping.get(state, state)}")

    # ------------------------------------------------------------------ #
    # Permission flow
    # ------------------------------------------------------------------ #
    def _ask_permission(self, request: PermissionRequest) -> PermissionDecision:
        result: dict[str, PermissionDecision] = {"decision": PermissionDecision.DENY}
        loop = QEventLoop()

        def _handle(req, holder):
            try:
                dlg = PermissionDialog(req, self)
                dlg.exec()
                holder["decision"] = dlg.decision
            finally:
                loop.quit()

        conn = self._permission_requested.connect(_handle)
        try:
            self._permission_requested.emit(request, result)
            loop.exec()
        finally:
            try:
                self._permission_requested.disconnect(conn)
            except (RuntimeError, TypeError):
                pass

        return result["decision"]

    # ------------------------------------------------------------------ #
    # Settings / misc
    # ------------------------------------------------------------------ #
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.permissions, self)
        dlg.config_saved.connect(self._on_config_saved)
        dlg.exec()

    def _on_config_saved(self, config: AppConfig) -> None:
        self.config = config
        self._apply_theme(config.theme)
        self._update_provider_label()
        self._set_status("Settings saved.")
        self._refresh_connection_status()

    def _about(self) -> None:
        QMessageBox.information(
            self,
            "About Local Coding Agent",
            "A local, permission-first coding agent.\n\n"
            "Supports GapGPT and DeepSeek as OpenAI-compatible backends.\n"
            "All file and command operations require your approval.",
        )

    def _prompt_first_run(self) -> None:
        answer = QMessageBox.question(
            self,
            "Welcome to Local Coding Agent",
            "Welcome!\n\n"
            "1. Enter your GapGPT (or DeepSeek) API key in Settings\n"
            "2. Choose a workspace folder\n"
            "3. Start chatting\n\n"
            "Open Settings now?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._open_settings()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.conversation.messages:
            self.conversation_store.save(self.conversation)
        if self.agent and self.agent.is_running:
            self.agent.cancel()
        super().closeEvent(event)


def _summarize_tool_call(name: str, args: dict) -> str:
    try:
        if name in (
            "read_file",
            "write_file",
            "delete_file",
            "create_file",
            "get_file_info",
        ):
            return str(args.get("path", ""))
        if name in ("move_file", "copy_file"):
            return f"{args.get('source','?')} → {args.get('destination','?')}"
        if name == "run_command":
            return str(args.get("command", ""))[:80]
        if name in ("search_text", "search_files"):
            return str(args.get("query") or args.get("pattern") or "")[:80]
        if name == "replace_text":
            return f"{args.get('path','?')}"
        return ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
    except Exception:  # noqa: BLE001
        return ""
