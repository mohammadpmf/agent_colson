"""Read-only Git tools (status/diff/log/branch)."""

from __future__ import annotations

import subprocess
from typing import Any

from .base import Tool, ToolContext, ToolResult


def _git(cwd: str, *args: str, timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", "git executable not found on PATH."
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out."


class GitStatusTool(Tool):
    name = "git_status"
    description = "Show `git status --short` output for the workspace."

    @property
    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        code, out, err = _git(str(ctx.workspace.root), "status", "--short", "--branch")
        if code != 0:
            return ToolResult(ok=False, error=err or "git failed")
        return ToolResult(ok=True, output=out or "(clean)")


class GitDiffTool(Tool):
    name = "git_diff"
    description = "Show `git diff` (optionally for a specific file)."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Optional file path."},
                "staged": {"type": "boolean", "default": False},
            },
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        args = ["diff"]
        if arguments.get("staged"):
            args.append("--cached")
        if arguments.get("path"):
            try:
                p = ctx.workspace.resolve(arguments["path"])
            except Exception as exc:  # noqa: BLE001
                return ToolResult(ok=False, error=str(exc))
            args.append("--")
            args.append(str(p))
        code, out, err = _git(str(ctx.workspace.root), *args)
        if code != 0:
            return ToolResult(ok=False, error=err or "git failed")
        return ToolResult(ok=True, output=out or "(no differences)")


class GitLogTool(Tool):
    name = "git_log"
    description = "Show recent commit history."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                }
            },
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        limit = int(arguments.get("limit", 20))
        code, out, err = _git(
            str(ctx.workspace.root), "log", f"-n{limit}", "--oneline", "--decorate"
        )
        if code != 0:
            return ToolResult(ok=False, error=err or "git failed")
        return ToolResult(ok=True, output=out or "(no commits)")


class GitBranchTool(Tool):
    name = "git_branch"
    description = "List local branches."

    @property
    def schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        code, out, err = _git(str(ctx.workspace.root), "branch", "-vv")
        if code != 0:
            return ToolResult(ok=False, error=err or "git failed")
        return ToolResult(ok=True, output=out or "(no branches)")
