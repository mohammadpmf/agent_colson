"""Conversation dataclasses."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class StoredMessage:
    role: str
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StoredMessage":
        return cls(
            role=raw.get("role", "user"),
            content=raw.get("content", ""),
            timestamp=raw.get("timestamp", time.time()),
            tool_calls=list(raw.get("tool_calls", [])),
            tool_call_id=raw.get("tool_call_id"),
            tool_name=raw.get("tool_name"),
        )


@dataclass
class Conversation:
    id: str = field(default_factory=_new_id)
    title: str = "New Chat"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    workspace: str = ""
    model: str = "deepseek-chat"
    messages: list[StoredMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace": self.workspace,
            "model": self.model,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Conversation":
        return cls(
            id=raw.get("id", _new_id()),
            title=raw.get("title", "New Chat"),
            created_at=raw.get("created_at", time.time()),
            updated_at=raw.get("updated_at", time.time()),
            workspace=raw.get("workspace", ""),
            model=raw.get("model", "deepseek-chat"),
            messages=[StoredMessage.from_dict(m) for m in raw.get("messages", [])],
        )
