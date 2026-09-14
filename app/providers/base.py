"""Abstract provider interface + shared dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Protocol


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
        """Serialize into the OpenAI-compatible chat format."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json_dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class LLMResponse:
    """A complete (non-streamed) response from the model."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0


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
    ) -> LLMResponse:
        """Send a chat request and return the final response."""
        ...

    def is_configured(self) -> bool:
        """Return True if the provider has credentials."""
        ...

    def test_connection(self) -> tuple[bool, str]:
        """Verify credentials. Returns (ok, message)."""
        ...


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)
