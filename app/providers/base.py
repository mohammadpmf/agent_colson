"""Abstract provider interface + shared dataclasses."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class ToolCall:
    """A structured tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    """A single message in the conversation."""

    role: str  # system | user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_api(self) -> dict[str, Any]:
        """Serialize into the OpenAI-compatible chat format.

        Strict rules enforced here:
          * assistant + tool_calls => content must be null (not "")
          * tool messages must have a non-empty tool_call_id
          * tool messages must have non-empty content
        """
        msg: dict[str, Any] = {"role": self.role}

        if self.role == "assistant" and self.tool_calls:
            msg["content"] = None
            msg["tool_calls"] = [
                {
                    "id": tc.id or f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json_dumps(tc.arguments),
                    },
                }
                for i, tc in enumerate(self.tool_calls)
            ]
            return msg

        if self.role == "tool":
            if not self.tool_call_id:
                self.tool_call_id = "call_orphan"
            if not self.content:
                self.content = "(empty tool result)"
            msg["tool_call_id"] = self.tool_call_id
            if self.name:
                msg["name"] = self.name
            msg["content"] = self.content
            return msg

        msg["content"] = self.content or ""
        return msg


class LLMProvider(Protocol):
    """Interface that all providers must implement."""

    name: str

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> "LLMResponse": ...

    def is_configured(self) -> bool: ...

    def test_connection(self) -> tuple[bool, str]: ...


@dataclass
class LLMResponse:
    """A complete (non-streamed) response from the model."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)
