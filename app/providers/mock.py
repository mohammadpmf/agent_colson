"""Deterministic mock provider for tests and offline demos."""

from __future__ import annotations

from typing import Any, Callable

from .base import ChatMessage, LLMProvider, LLMResponse, ToolCall


class MockDeepSeekProvider(LLMProvider):
    """A provider that replays scripted responses — used in unit tests."""

    name = "mock"

    def __init__(self, scripted: list[LLMResponse] | None = None) -> None:
        self.scripted = list(scripted or [])
        self.calls: list[list[ChatMessage]] = []

    def is_configured(self) -> bool:
        return True

    def test_connection(self) -> tuple[bool, str]:
        return True, "Mock provider ready"

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
        on_token: Callable[[str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
    ) -> LLMResponse:
        self.calls.append(list(messages))
        if not self.scripted:
            return LLMResponse(content="(mock) done", finish_reason="stop")

        resp = self.scripted.pop(0)
        if stream and on_token and resp.content:
            for chunk in _chunk(resp.content, 8):
                if cancel_flag and cancel_flag():
                    break
                on_token(chunk)
        return resp


def _chunk(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]
