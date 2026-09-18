import logging
import os
import tempfile
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from app.agent import AgentEngine, AgentEventType, AgentMode, AgentState
from app.config import AppConfig
from app.context import ContextManager
from app.context.history import repair_history
from app.conversations import Conversation, ConversationStore, StoredMessage
from app.logging_setup import _RedactingFilter
from app.permissions import PermissionAction, PermissionDecision, PermissionManager, PermissionRequest
from app.permissions.storage import PermissionStorage
from app.providers import ChatMessage, LLMResponse, MockDeepSeekProvider, ToolCall
from app.tools import ToolContext, build_default_registry
from app.tools.filesystem import DeleteFileTool, WriteFileTool
from app.tools.search import SearchTextTool
from app.tools.terminal import RunCommandTool
from app.tools.base import ToolResult
from app.ui.chat_view import render_markdown
from app.ui.main_window import MainWindow
from app.ui.workers import run_in_thread
from app.workspace import WorkspaceManager

APP = QApplication.instance() or QApplication([])


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.permissions = PermissionManager(PermissionStorage(self.root / "agent.db"), self.root,
                                             lambda _: PermissionDecision.ALLOW_ONCE)
        self.context = ToolContext(WorkspaceManager(self.root), self.permissions)

    def tearDown(self):
        self.temporary.cleanup()

    def test_persian_markdown_does_not_corrupt_markup(self):
        doc = QTextDocument()
        doc.setHtml(render_markdown('سلام **دنیا** با `Python` & <tag>\n\nHello فارسی\n\n```python\nprint("سلام")\n```'))
        text = doc.toPlainText()
        self.assertIn('سلام دنیا با Python & <tag>', text)
        self.assertNotIn('span', text)
        blocks = []
        block = doc.begin()
        while block.isValid():
            blocks.append((block.text(), block.blockFormat().layoutDirection(), block.blockFormat().alignment()))
            block = block.next()
        self.assertEqual(blocks[0][1], Qt.RightToLeft)
        self.assertTrue(blocks[0][2] & Qt.AlignRight)
        self.assertEqual(next(b[1] for b in blocks if b[0].startswith('Hello')), Qt.LeftToRight)
        self.assertEqual(next(b[1] for b in blocks if b[0].startswith('print')), Qt.LeftToRight)

    def test_code_and_html_are_literal(self):
        doc = QTextDocument()
        doc.setHtml(render_markdown('```html\n<b>x & y</b>\n```\n\n<img src="file:///secret">'))
        self.assertIn('<b>x & y</b>', doc.toPlainText())
        self.assertIn('<img', doc.toPlainText())

    def test_atomic_save_and_load(self):
        store = ConversationStore(self.root / "chats")
        chat = Conversation(title="گفتگو", messages=[StoredMessage(role="user", content="سلام")])
        self.assertTrue(store.save(chat))
        self.assertEqual(store.load(chat.id).messages[0].content, "سلام")
        with patch.object(Path, "replace", side_effect=OSError("disk")):
            chat.title = "new"
            self.assertFalse(store.save(chat))
        self.assertEqual(store.load(chat.id).title, "گفتگو")
        self.assertEqual(len(list(store.base_dir.iterdir())), 1)

    def test_corrupt_chat_is_skipped(self):
        store = ConversationStore(self.root / "chats")
        (store.base_dir / "broken.json").write_text('[]')
        self.assertEqual(store.list_all(), [])

    def test_multiple_tool_calls_and_interruption_repaired(self):
        history = repair_history([
            ChatMessage(role="assistant", tool_calls=[ToolCall("a", "one", {})]),
            ChatMessage(role="assistant", tool_calls=[ToolCall("b", "two", {})]),
            ChatMessage(role="tool", tool_call_id="a", content="ok"),
            ChatMessage(role="user", content="continue"),
        ])
        self.assertEqual([m.role for m in history], ["assistant", "tool", "tool", "user"])
        self.assertEqual([t.id for t in history[0].tool_calls], ["a", "b"])
        self.assertEqual(history[2].tool_call_id, "b")

    def test_context_never_splits_tool_exchange(self):
        messages = [ChatMessage(role="user", content="x" * 1000),
                    ChatMessage(role="assistant", tool_calls=[ToolCall("a", "read", {})]),
                    ChatMessage(role="tool", tool_call_id="a", content="result"),
                    ChatMessage(role="user", content="continue")]
        trimmed = ContextManager(max_tokens=60, keep_last=2).trim(messages)
        self.assertEqual(trimmed, repair_history(trimmed))
        self.assertEqual(trimmed[-1].content, "continue")

    def test_nonstream_response_emitted_once(self):
        events = []
        provider = MockDeepSeekProvider([LLMResponse(content="answer")])
        engine = AgentEngine(provider, build_default_registry(), self.context,
                             emit=events.append, streaming=False)
        engine._run([], "hello")
        self.assertEqual(len([e for e in events if e.type == AgentEventType.ASSISTANT_MESSAGE]), 1)
        self.assertEqual(engine.state, AgentState.COMPLETED)

    def test_provider_error_is_failed(self):
        provider = MockDeepSeekProvider()
        with patch.object(provider, "chat", side_effect=RuntimeError("offline")):
            engine = AgentEngine(provider, build_default_registry(), self.context)
            engine._run([], "hello")
        self.assertEqual(engine.state, AgentState.FAILED)

    def test_ask_mode_does_not_execute_tool_calls(self):
        provider = MockDeepSeekProvider([LLMResponse(tool_calls=[ToolCall("a", "create_file", {"path": "bad"})])])
        engine = AgentEngine(provider, build_default_registry(), self.context, mode=AgentMode.ASK)
        engine._run([], "hello")
        self.assertFalse((self.root / "bad").exists())

    def test_dangerous_permission_always_prompts_and_allow_once_works(self):
        self.permissions.ask_callback = lambda _: PermissionDecision.ALWAYS_ALLOW
        request = PermissionRequest(PermissionAction.DELETE_FILE, str(self.root / "victim"), dangerous=True)
        self.permissions.check(request)
        self.assertEqual(self.permissions.list_rules(), [])
        self.permissions.ask_callback = lambda _: PermissionDecision.ALLOW_ONCE
        (self.root / "victim").write_text("test")
        self.assertTrue(DeleteFileTool().execute({"path": "victim"}, self.context).ok)

    def test_cancel_permission_never_writes(self):
        self.permissions.ask_callback = lambda _: PermissionDecision.CANCEL
        self.assertFalse(WriteFileTool().execute({"path": "new", "content": "x"}, self.context).ok)
        self.assertFalse((self.root / "new").exists())

    def test_workspace_rules_do_not_leak(self):
        self.permissions.ask_callback = lambda _: PermissionDecision.ALWAYS_ALLOW
        self.permissions.check(PermissionRequest(PermissionAction.READ_FILE, str(self.root / "a")))
        other = self.root / "other"
        other.mkdir()
        self.permissions.set_workspace(other)
        self.permissions.ask_callback = lambda _: PermissionDecision.DENY
        decision = self.permissions.check(PermissionRequest(PermissionAction.READ_FILE, str(other / "b")))
        self.assertEqual(decision, PermissionDecision.DENY)

    def test_logging_does_not_append_secret_after_redaction(self):
        record = logging.LogRecord("test", 20, "", 1, "password=verysecret token=hidden123", (), None)
        _RedactingFilter().filter(record)
        self.assertNotIn("verysecret", record.getMessage())
        self.assertNotIn("hidden123", record.getMessage())

    def test_failed_command_keeps_diagnostic_output(self):
        self.assertIn("SyntaxError", ToolResult(False, "SyntaxError", "exit 1").to_model_string())

    def test_saved_chat_opens_and_continues_in_same_file(self):
        config = AppConfig(data_dir=self.root / "data", workspace=str(self.root))
        with patch.object(MainWindow, "_refresh_connection_status"), patch.object(MainWindow, "_prompt_first_run"):
            window = MainWindow(config)
            try:
                chat = Conversation(workspace=str(self.root), messages=[StoredMessage(role="user", content="سلام")])
                window.conversation_store.save(chat)
                window._refresh_recent_chats()
                window.explorer.recent.itemClicked.emit(window.explorer.recent.item(0))
                self.assertEqual(window.conversation.id, chat.id)
                self.assertEqual(window._build_api_history()[0].content, "سلام")
                window.config.gapgpt_api_key = "test-only"
                with patch.object(window, "_make_provider", return_value=MockDeepSeekProvider([LLMResponse(content="پاسخ")])):
                    window.input.setPlainText("ادامه")
                    self.assertEqual(window.input.document().begin().blockFormat().layoutDirection(), Qt.RightToLeft)
                    window._send()
                    window._new_chat()
                    self.assertEqual(window.conversation.id, chat.id)
                    deadline = time.monotonic() + 3
                    while window._busy and time.monotonic() < deadline:
                        APP.processEvents()
                        time.sleep(.01)
                self.assertFalse(window._busy)
                saved = window.conversation_store.load(chat.id)
                self.assertEqual([m.content for m in saved.messages], ["سلام", "ادامه", "پاسخ"])
                self.assertEqual(len(window.conversation_store.list_all()), 1)
            finally:
                window.close()
                window.deleteLater()
                APP.processEvents()

    def test_worker_callbacks_run_on_gui_thread(self):
        results = []
        thread, worker = run_in_thread(APP, lambda: "ok", lambda result: results.append((result, QThread.currentThread())))
        deadline = time.monotonic() + 3
        while not results and time.monotonic() < deadline:
            APP.processEvents()
            time.sleep(.01)
        self.assertEqual(results, [("ok", APP.thread())])
        for _ in range(5):
            APP.processEvents()

    def test_dangerous_command_accepts_once_without_executing_real_command(self):
        import subprocess
        with patch("app.tools.terminal.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "ok", "")) as run:
            result = RunCommandTool().execute({"command": "rm -rf demo"}, self.context)
            self.assertTrue(result.ok)
            run.assert_called_once()

    def test_search_excludes_ignored_and_secret_files(self):
        (self.root / "normal.py").write_text("needle")
        (self.root / ".env").write_text("needle")
        (self.root / "config.py").write_text("password='needleSecret'")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "large.js").write_text("needle")
        result = SearchTextTool().execute({"query": "needle"}, self.context)
        self.assertEqual(result.data["count"], 1)
        self.assertIn("normal.py", result.output)

    def test_permission_dialog_is_on_gui_thread(self):
        with patch.object(MainWindow, "_refresh_connection_status"):
            window = MainWindow(AppConfig(data_dir=self.root / "data", workspace=str(self.root)))
            seen = []
            decisions = []
            class FakeDialog:
                decision = PermissionDecision.ALLOW_ONCE
                def __init__(self, request, parent):
                    seen.append(QThread.currentThread())
                def exec(self):
                    return 0
            request = PermissionRequest(PermissionAction.READ_FILE, str(self.root))
            with patch("app.ui.main_window.PermissionDialog", FakeDialog):
                worker = threading.Thread(target=lambda: decisions.append(window._ask_permission(request)))
                worker.start()
                deadline = time.monotonic() + 3
                while worker.is_alive() and time.monotonic() < deadline:
                    APP.processEvents()
                    time.sleep(.01)
                worker.join(timeout=.1)
            self.assertEqual(seen, [APP.thread()])
            self.assertEqual(decisions, [PermissionDecision.ALLOW_ONCE])
            window.close()

    def test_gapgpt_stream_error_does_not_retry_and_duplicate_output(self):
        from app.providers import GapGPTProvider, GapGPTError
        provider = GapGPTProvider("test-only")
        with patch.object(provider, "_stream_chat", side_effect=GapGPTError("offline")), patch.object(provider, "_blocking_chat") as fallback:
            with self.assertRaises(GapGPTError):
                provider.chat([ChatMessage(role="user", content="test")])
            fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
