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

    Strategy:
      1. Always keep the system prompt.
      2. Always keep the last N user/assistant turns.
      3. When over budget, summarize the middle into a single system note.
    """

    def __init__(self, max_tokens: int = 32_000, keep_last: int = 12) -> None:
        self.max_tokens = max_tokens
        self.keep_last = keep_last
        self.stats = ContextStats()

    def trim(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        if not messages:
            self.stats = ContextStats()
            return []

        system_msgs = [m for m in messages if m.role == "system"]
        convo = [m for m in messages if m.role != "system"]

        total = sum(estimate_tokens(m.content) for m in messages)
        self.stats.total_messages = len(messages)

        if total <= self.max_tokens:
            return list(messages)

        # Keep the last `keep_last` messages verbatim.
        recent = convo[-self.keep_last :] if len(convo) > self.keep_last else convo
        older = convo[: len(convo) - len(recent)]

        summary_lines = []
        for m in older:
            snippet = m.content.strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:160] + "…"
            summary_lines.append(f"- [{m.role}] {snippet}")
        summary_text = (
            "Earlier conversation summary (auto-generated, may be lossy):\n"
            + "\n".join(summary_lines[-30:])
        )

        trimmed = (
            list(system_msgs)
            + [ChatMessage(role="system", content=summary_text)]
            + list(recent)
        )

        # Ensure we're actually under budget.
        while (
            sum(estimate_tokens(m.content) for m in trimmed) > self.max_tokens
            and len(trimmed) > len(system_msgs) + 1
        ):
            trimmed.pop(len(system_msgs))  # drop oldest summary line

        self.stats.dropped_messages = len(older)
        self.stats.summarized = True
        return trimmed
