"""Token-aware context window management."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.providers import ChatMessage
from .history import message_groups

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
    even if it alone exceeds the estimated budget. Older messages are kept as
    bounded excerpts when space remains after retaining recent exchanges.
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

        self.stats = ContextStats(total_messages=len(messages))
        shrunk = [self._shrink_tool_result(m) for m in messages]
        systems = [m for m in shrunk if m.role == "system"]
        groups = message_groups([m for m in shrunk if m.role != "system"])

        def cost(items):
            return sum(estimate_tokens(json.dumps(m.to_api(), ensure_ascii=False)) + 4 for m in items)

        # Drop complete exchanges, never a tool parent without its results.
        budget = cost(systems) + sum(cost(group) for group in groups)
        removed_messages: list[ChatMessage] = []
        while budget > self.max_tokens and len(groups) > 1:
            removed = groups.pop(0)
            budget -= cost(removed)
            removed_messages.extend(removed)

        summary: list[ChatMessage] = []
        if removed_messages:
            # This is an extractive, lossy summary, not an LLM-generated one.
            # Use the remaining budget without evicting additional recent turns.
            excerpts = []
            for message in reversed(removed_messages[-40:]):
                snippet = " ".join(message.content.split())[:120]
                if message.tool_calls:
                    snippet = "Tools: " + ", ".join(call.name for call in message.tool_calls)
                if snippet:
                    excerpts.append(f"[{message.role}] {snippet}")
            text = "\n".join(excerpts)
            prefix = "Earlier messages (lossy excerpts, newest first):\n"
            low, high = 1, len(text)
            while low <= high:
                length = (low + high) // 2
                content = prefix + text[:length] + ("…" if length < len(text) else "")
                candidate = [ChatMessage(role="system", content=content)]
                if budget + cost(candidate) <= self.max_tokens:
                    summary = candidate
                    low = length + 1
                else:
                    high = length - 1

        self.stats.dropped_messages = len(removed_messages)
        self.stats.summarized = bool(summary)
        budget += cost(summary)
        self.stats.input_tokens = budget
        return systems + summary + [message for group in groups for message in group]

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
