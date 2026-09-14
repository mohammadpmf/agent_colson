"""Search tools: filename globs + full-text grep."""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any

from app.permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
)
from app.security import SecurityViolation

from .base import Tool, ToolContext, ToolResult

MAX_RESULTS = 200
MAX_FILE_BYTES = 512 * 1024


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Find files by name pattern (glob, e.g. '*.py')."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern like '*.py'",
                },
                "path": {"type": "string", "default": "."},
            },
            "required": ["pattern"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            base = ctx.workspace.resolve(arguments.get("path", "."))
            pattern = arguments["pattern"]
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.READ_FILE,
                target=str(base),
                reason=f"Search files matching {pattern}",
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied search.")

        results: list[str] = []
        for p in base.rglob("*"):
            if len(results) >= MAX_RESULTS:
                break
            if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                try:
                    results.append(p.relative_to(ctx.workspace.root).as_posix())
                except ValueError:
                    continue
        return ToolResult(
            ok=True,
            output="\n".join(results) if results else "(no matches)",
            data={"count": len(results)},
        )


class SearchTextTool(Tool):
    name = "search_text"
    description = "Search for text or a regex across files in the workspace."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string", "default": "."},
                "regex": {"type": "boolean", "default": False},
                "extensions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list like ['.py', '.js']",
                },
            },
            "required": ["query"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            base = ctx.workspace.resolve(arguments.get("path", "."))
            query = arguments["query"]
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not query:
            return ToolResult(ok=False, error="Empty query.")

        use_regex = bool(arguments.get("regex", False))
        exts = [e.lower() for e in (arguments.get("extensions") or [])]

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.READ_FILE,
                target=str(base),
                reason=f"Search text: {query[:60]}",
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied search.")

        try:
            matcher = re.compile(
                query if use_regex else re.escape(query), re.IGNORECASE
            )
        except re.error as exc:
            return ToolResult(ok=False, error=f"Bad regex: {exc}")

        matches: list[str] = []
        total = 0
        for path in base.rglob("*"):
            if total >= MAX_RESULTS:
                break
            if not path.is_file():
                continue
            if exts and path.suffix.lower() not in exts:
                continue
            if not ctx.workspace.is_text_file(path):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(content.splitlines(), start=1):
                if matcher.search(line):
                    rel = path.relative_to(ctx.workspace.root).as_posix()
                    snippet = line.strip()[:160]
                    matches.append(f"{rel}:{i}: {snippet}")
                    total += 1
                    if total >= MAX_RESULTS:
                        break

        return ToolResult(
            ok=True,
            output="\n".join(matches) if matches else "(no matches)",
            data={"count": total},
        )
