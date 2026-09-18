"""Token-aware context window management."""

from __future__ import annotations

from dataclasses import dataclass

from app.providers import ChatMessage

# Rough token estimate — 1 token ≈ 4 characters of English text.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass
class ContextStats:
    input_tokens: int = 0
    output_tokens: int = 0
    total_messages: int = 0
    dropped_messages: int = 0
    summarized: bool = False


class ContextManager:
    """Trim older complete exchanges while preserving system messages.

    Tool results are shortened first. The newest exchange is always retained,
    even if it alone exceeds the estimated budget. keep_last is accepted for
    compatibility; protocol integrity takes priority over message counts.
    """

    def __init__(
        self,
        max_tokens: int = 32_000,
        keep_last: int = 12,
        max_tool_result_chars: int = 4_000,
    ) -> None:
        self.max_tokens = max_tokens
        self.keep_last = keep_last
        self.max_tool_result_chars = max_tool_result_chars
        self.stats = ContextStats()

    def trim(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if not messages:
            self.stats = ContextStats()
            return []

        from .history import message_groups
        import json

        self.stats = ContextStats(total_messages=len(messages))
        shrunk = [self._shrink_tool_result(m) for m in messages]
        systems = [m for m in shrunk if m.role == "system"]
        groups = message_groups([m for m in shrunk if m.role != "system"])

        def cost(items):
            return sum(estimate_tokens(json.dumps(m.to_api(), ensure_ascii=False)) + 4 for m in items)

        # Drop complete exchanges, never a tool parent without its results.
        budget = cost(systems) + sum(cost(group) for group in groups)
        while budget > self.max_tokens and len(groups) > 1:
            removed = groups.pop(0)
            budget -= cost(removed)
            self.stats.dropped_messages += len(removed)
        self.stats.input_tokens = budget
        return systems + [message for group in groups for message in group]

    # ------------------------------------------------------------------ #
    def _shrink_tool_result(self, message: ChatMessage) -> ChatMessage:
        """Return a copy of `message` with the content truncated if needed."""
        if message.role != "tool":
            return message
        limit = self.max_tool_result_chars
        if len(message.content) <= limit:
            return message
        head = message.content[: limit // 2]
        tail = message.content[-limit // 2 :]
        truncated = f"{head}\n\n... [truncated {len(message.content) - limit} chars] ...\n\n{tail}"
        return ChatMessage(
            role=message.role,
            content=truncated,
            tool_call_id=message.tool_call_id,
            name=message.name,
        )
