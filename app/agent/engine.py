"""The agent execution engine — think → tool → observe → repeat."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.context import ContextManager
from app.permissions import (
    PermissionDecision,
    PermissionRequest,
)
from app.providers import (
    ChatMessage,
    DeepSeekError,
    GapGPTError,
    LLMProvider,
    LLMResponse,
    ToolCall,
)
from app.tools import Tool, ToolContext, ToolRegistry

from .prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)


MAX_TOOL_ITERATIONS = 25


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    WAITING_FOR_API = "waiting_for_api"
    RUNNING = "running"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class AgentMode(str, Enum):
    ASK = "ask"
    AGENT = "agent"


class AgentEventType(str, Enum):
    STATE = "state"
    ASSISTANT_TOKEN = "assistant_token"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_DENIED = "tool_denied"
    ERROR = "error"
    USAGE = "usage"
    DONE = "done"
    PLAN = "plan"


@dataclass
class AgentEvent:
    type: AgentEventType
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class AgentEngine:
    """Drives the tool-calling loop in a background thread."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        tool_context: ToolContext,
        mode: AgentMode = AgentMode.AGENT,
        emit: Callable[[AgentEvent], None] | None = None,
        context_manager: ContextManager | None = None,
        streaming: bool = True,
    ) -> None:
        self.provider = provider
        self.registry = registry
        self.tool_context = tool_context
        self.mode = mode
        self.streaming = streaming
        self.emit = emit or (lambda _e: None)
        self.context_manager = context_manager or ContextManager()

        self.state = AgentState.IDLE
        self.usage = UsageStats()

        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def cancel(self) -> None:
        self._cancel.set()

    def start(
        self,
        history: list[ChatMessage],
        user_input: str | None = None,
    ) -> None:
        if self.is_running:
            raise RuntimeError("Agent is already running.")
        self._cancel.clear()
        self.state = AgentState.PLANNING
        self._emit_state()

        self._thread = threading.Thread(
            target=self._run,
            args=(list(history), user_input),
            name="AgentEngine",
            daemon=True,
        )
        self._thread.start()

    def _run(self, history: list[ChatMessage], user_input: str | None) -> None:
        log.info(
            "[engine] _run started (history=%d, user_input=%s)",
            len(history),
            bool(user_input),
        )
        try:
            messages: list[ChatMessage] = [
                ChatMessage(role="system", content=SYSTEM_PROMPT)
            ]
            messages.extend(history)
            if user_input:
                messages.append(ChatMessage(role="user", content=user_input))

            tools = (
                self.registry.openai_schemas() if self.mode == AgentMode.AGENT else []
            )

            for iteration in range(MAX_TOOL_ITERATIONS):
                if self._cancel.is_set():
                    self._finish(AgentState.CANCELED if self._cancel.is_set() else AgentState.FAILED)
                    return

                log.info("[engine] iteration %d — calling LLM", iteration)
                self.state = AgentState.WAITING_FOR_API
                self._emit_state()

                trimmed = self.context_manager.trim(messages)
                response = self._call_llm(trimmed, tools)
                if response is None:
                    log.info("[engine] LLM returned None (cancel or error)")
                    self._finish(AgentState.CANCELED if self._cancel.is_set() else AgentState.FAILED)
                    return

                log.info(
                    "[engine] LLM response: content=%d chars, tool_calls=%d, finish=%s",
                    len(response.content or ""),
                    len(response.tool_calls or []),
                    response.finish_reason,
                )

                self.usage.input_tokens += response.input_tokens
                self.usage.output_tokens += response.output_tokens
                self.emit(
                    AgentEvent(
                        AgentEventType.USAGE,
                        {
                            "input": self.usage.input_tokens,
                            "output": self.usage.output_tokens,
                            "total": self.usage.total,
                        },
                    )
                )

                if response.content:
                    self.emit(
                        AgentEvent(
                            AgentEventType.ASSISTANT_MESSAGE,
                            {"content": response.content},
                        )
                    )

                if self.mode == AgentMode.ASK and response.tool_calls:
                    raise RuntimeError("Provider returned tool calls in Ask mode.")

                if not response.tool_calls:
                    self._finish(AgentState.COMPLETED)
                    return

                # Emit TOOL_CALL events FIRST so the UI can store them as
                # assistant tool-call messages in history before the tool
                # results are appended. This keeps the pairing intact:
                #   assistant(tool_calls)  ->  tool(result)  ->  ...
                for call in response.tool_calls:
                    self.emit(
                        AgentEvent(
                            AgentEventType.TOOL_CALL,
                            {
                                "id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        )
                    )

                # The API-side payload uses a single assistant message with
                # the tool calls (content null). We DO NOT include any text
                # alongside tool_calls, because some OpenAI-compatible
                # backends reject that.
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content="",
                        tool_calls=response.tool_calls,
                    )
                )

                for call in response.tool_calls:
                    if self._cancel.is_set():
                        self._finish(AgentState.CANCELED)
                        return
                    result_msg = self._execute_tool(call)
                    messages.append(result_msg)

            self.emit(
                AgentEvent(
                    AgentEventType.ERROR,
                    {
                        "message": f"Reached max tool iterations ({MAX_TOOL_ITERATIONS})."
                    },
                )
            )
            self._finish(AgentState.FAILED)

        except Exception as exc:  # noqa: BLE001
            log.exception("Agent loop crashed")
            self.emit(AgentEvent(AgentEventType.ERROR, {"message": str(exc)}))
            self._finish(AgentState.FAILED)

    def _call_llm(
        self, messages: list[ChatMessage], tools: list[dict[str, Any]]
    ) -> LLMResponse | None:
        def on_token(piece: str) -> None:
            self.emit(AgentEvent(AgentEventType.ASSISTANT_TOKEN, {"delta": piece}))

        self.state = AgentState.RUNNING
        self._emit_state()

        try:
            response = self.provider.chat(
                messages=messages,
                tools=tools or None,
                stream=self.streaming,
                on_token=on_token,
                cancel_flag=self._cancel.is_set,
            )
        except (DeepSeekError, GapGPTError) as exc:
            log.error("[engine] provider error: %s", exc)
            self.emit(AgentEvent(AgentEventType.ERROR, {"message": str(exc)}))
            return None
        except Exception as exc:  # noqa: BLE001
            log.exception("[engine] provider.chat crashed")
            self.emit(AgentEvent(AgentEventType.ERROR, {"message": str(exc)}))
            return None

        if self._cancel.is_set():
            return None

        return response

    def _execute_tool(self, call: ToolCall) -> ChatMessage:
        tool: Tool | None = self.registry.get(call.name)

        if tool is None:
            output = f"ERROR: unknown tool '{call.name}'"
            self.emit(
                AgentEvent(
                    AgentEventType.TOOL_RESULT,
                    {
                        "id": call.id,
                        "name": call.name,
                        "ok": False,
                        "output": output,
                    },
                )
            )
            return ChatMessage(
                role="tool", content=output, tool_call_id=call.id, name=call.name
            )

        if not isinstance(call.arguments, dict):
            output = "ERROR: tool arguments must be a JSON object."
            self.emit(
                AgentEvent(
                    AgentEventType.TOOL_RESULT,
                    {
                        "id": call.id,
                        "name": call.name,
                        "ok": False,
                        "output": output,
                    },
                )
            )
            return ChatMessage(
                role="tool", content=output, tool_call_id=call.id, name=call.name
            )

        self.state = AgentState.WAITING_FOR_PERMISSION
        self._emit_state()

        try:
            result = tool.execute(call.arguments, self.tool_context)
        except Exception as exc:  # noqa: BLE001
            log.exception("Tool %s crashed", call.name)
            result_ok = False
            output = f"ERROR: tool crashed: {exc}"
        else:
            result_ok = result.ok
            output = result.to_model_string()

        self.state = AgentState.RUNNING
        self._emit_state()

        self.emit(
            AgentEvent(
                AgentEventType.TOOL_RESULT,
                {
                    "id": call.id,
                    "name": call.name,
                    "ok": result_ok,
                    "output": output,
                },
            )
        )

        return ChatMessage(
            role="tool", content=output, tool_call_id=call.id, name=call.name
        )

    def _emit_state(self) -> None:
        self.emit(AgentEvent(AgentEventType.STATE, {"state": self.state.value}))

    def _finish(self, state: AgentState) -> None:
        self.state = state
        self._emit_state()
        self.emit(AgentEvent(AgentEventType.DONE, {"state": state.value}))


def parse_tool_arguments(raw: str | dict[str, Any]) -> dict[str, Any]:
    """Safely parse a raw tool-call argument payload (never use eval)."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return value if isinstance(value, dict) else {"_value": value}
