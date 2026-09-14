"""Tool registry + factory."""

from __future__ import annotations

from typing import Iterator

from .base import Tool


class ToolRegistry:
    """Holds a set of named tools."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("Tool must define a name.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def openai_schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())


def build_default_registry() -> ToolRegistry:
    from .filesystem import (
        ListDirectoryTool,
        ReadFileTool,
        WriteFileTool,
        CreateFileTool,
        DeleteFileTool,
        MoveFileTool,
        CopyFileTool,
        GetFileInfoTool,
        ReplaceTextTool,
    )
    from .search import SearchFilesTool, SearchTextTool
    from .terminal import RunCommandTool
    from .git_tools import (
        GitStatusTool,
        GitDiffTool,
        GitLogTool,
        GitBranchTool,
    )

    reg = ToolRegistry()
    for tool in (
        ListDirectoryTool(),
        ReadFileTool(),
        WriteFileTool(),
        CreateFileTool(),
        DeleteFileTool(),
        MoveFileTool(),
        CopyFileTool(),
        GetFileInfoTool(),
        ReplaceTextTool(),
        SearchFilesTool(),
        SearchTextTool(),
        RunCommandTool(),
        GitStatusTool(),
        GitDiffTool(),
        GitLogTool(),
        GitBranchTool(),
    ):
        reg.register(tool)
    return reg
