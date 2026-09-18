"""Base classes for the tool system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.permissions import PermissionManager
from app.workspace import WorkspaceManager


@dataclass
class ToolContext:
    """Everything a tool needs to run."""

    workspace: WorkspaceManager
    permissions: PermissionManager
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """The result of running a tool."""

    ok: bool
    output: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_model_string(self) -> str:
        if self.ok:
            return self.output or "(no output)"
        return f"ERROR: {self.error or 'unknown error'}\n{self.output}".strip()


class Tool(ABC):
    """Abstract tool with JSON schema."""

    name: str = ""
    description: str = ""
    dangerous: bool = False

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function schema."""

    @abstractmethod
    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Run the tool. Must never raise — return a failing ToolResult instead."""

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }
