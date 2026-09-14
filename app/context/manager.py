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
    """Keeps the chat history within the model's token budget.

    Strategy (in order):
      1. Always keep every system message.
      2. Always keep the last `keep_last` user/assistant turns.
      3. When a tool result is longer than `max_tool_result_chars`,
         truncate it in place with a marker.
      4. When still over budget, summarize the middle of the conversation
         into a single system note.
      5. As a last resort, drop older messages entirely.
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

        self.stats.total_messages = len(messages)

        # 1) Shrink long tool results in place (mutate a copy).
        shrunk = [self._shrink_tool_result(m) for m in messages]

        total = sum(estimate_tokens(m.content) for m in shrunk)
        if total <= self.max_tokens:
            return shrunk

        # 2) Separate system / non-system.
        system_msgs = [m for m in shrunk if m.role == "system"]
        convo = [m for m in shrunk if m.role != "system"]

        # 3) Keep the last `keep_last` messages verbatim.
        recent = convo[-self.keep_last :] if len(convo) > self.keep_last else convo
        older = convo[: len(convo) - len(recent)]

        # 4) Summarize the older half.
        summary_lines = []
        for m in older:
            snippet = m.content.strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:120] + "…"
            summary_lines.append(f"- [{m.role}] {snippet}")
        summary_text = (
            "Earlier conversation summary (auto-generated, may be lossy):\n"
            + "\n".join(summary_lines[-40:])
        )

        trimmed = (
            list(system_msgs)
            + [ChatMessage(role="system", content=summary_text)]
            + list(recent)
        )

        # 5) If still over budget, drop the summary and the oldest turns.
        while (
            sum(estimate_tokens(m.content) for m in trimmed) > self.max_tokens
            and len(trimmed) > len(system_msgs) + 2
        ):
            # Prefer dropping the summary before dropping recent turns.
            if len(trimmed) > len(system_msgs) + 1:
                trimmed.pop(len(system_msgs))  # remove summary line
            else:
                break

        self.stats.dropped_messages = len(older)
        self.stats.summarized = True
        return trimmed

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
