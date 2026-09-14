"""Filesystem tools: read/write/create/delete/move/copy/replace/info."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.permissions import (
    PermissionAction,
    PermissionRequest,
    PermissionDecision,
)
from app.security import SecurityViolation

from .base import Tool, ToolContext, ToolResult

MAX_READ_LINES = 2000


# ---------------------------------------------------------------------- #
class ListDirectoryTool(Tool):
    name = "list_directory"
    description = "List files and folders in a directory inside the workspace."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path. Default '.'"},
                "depth": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
            },
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        rel = arguments.get("path", ".")
        depth = int(arguments.get("depth", 1))
        try:
            resolved = ctx.workspace.resolve(rel)
        except SecurityViolation as exc:
            return ToolResult(ok=False, error=str(exc))

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.READ_FILE,
                target=str(resolved),
                reason=f"List directory {rel}",
                details={"depth": depth},
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied listing this directory.")

        entries = ctx.workspace.list_entries(rel, depth=depth)
        lines = []
        for e in entries:
            marker = "[D]" if e.is_dir else "   "
            rel_path = Path(e.path).relative_to(ctx.workspace.root).as_posix()
            size = "" if e.is_dir else f"  ({e.size} bytes)"
            lines.append(f"{marker} {rel_path}{size}")
        output = "\n".join(lines) if lines else "(empty)"
        return ToolResult(ok=True, output=output, data={"count": len(entries)})


# ---------------------------------------------------------------------- #
class ReadFileTool(Tool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file inside the workspace. "
        "Supports optional start_line / end_line (1-indexed, inclusive)."
    )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not path.exists() or not path.is_file():
            return ToolResult(ok=False, error=f"File not found: {path}")

        guard = ctx.workspace.guard()
        if not ctx.workspace.is_text_file(path):
            return ToolResult(ok=False, error="Binary file — refusing to read as text.")

        sensitive = guard.is_sensitive(path)
        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.READ_FILE,
                target=str(path),
                reason=(
                    "Read sensitive file"
                    if sensitive
                    else "Read file to inspect content"
                ),
                dangerous=sensitive,
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied reading this file.")

        text = _read_text(path)
        if text is None:
            return ToolResult(
                ok=False, error="Could not decode file (unknown encoding)."
            )

        secrets = guard.contains_secret(text)
        lines = text.splitlines()
        start = int(arguments.get("start_line", 1))
        end = int(arguments.get("end_line", len(lines)))
        start = max(1, start)
        end = min(len(lines), end)
        if end < start:
            return ToolResult(ok=False, error="end_line must be >= start_line")
        if end - start + 1 > MAX_READ_LINES:
            end = start + MAX_READ_LINES - 1

        numbered = "\n".join(f"{i:>5} | {lines[i - 1]}" for i in range(start, end + 1))
        header = (
            f"# {path.relative_to(ctx.workspace.root).as_posix()} "
            f"(lines {start}-{end} of {len(lines)})\n"
        )
        if secrets:
            header += "⚠️  This file may contain secrets (patterns matched).\n"
        return ToolResult(
            ok=True,
            output=header + numbered,
            data={
                "total_lines": len(lines),
                "start": start,
                "end": end,
                "secrets": secrets,
            },
        )


# ---------------------------------------------------------------------- #
class WriteFileTool(Tool):
    name = "write_file"
    description = "Overwrite an existing file with new content. Prefer replace_text for small edits."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
            content = arguments["content"]
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.WRITE_FILE,
                target=str(path),
                reason="Write new content to file",
                details={"new_size": len(content)},
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied writing this file.")

        backup = _make_backup(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, error=f"Write failed: {exc}")
        return ToolResult(
            ok=True,
            output=f"Wrote {len(content)} bytes to {path.name}.",
            data={"path": str(path), "backup": str(backup) if backup else ""},
        )


# ---------------------------------------------------------------------- #
class CreateFileTool(Tool):
    name = "create_file"
    description = "Create a new file. Fails if the file already exists."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string", "default": ""},
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
            content = arguments.get("content", "")
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if path.exists():
            return ToolResult(ok=False, error=f"File already exists: {path.name}")

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.CREATE_FILE,
                target=str(path),
                reason="Create a new file",
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied creating this file.")

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, error=f"Create failed: {exc}")
        return ToolResult(
            ok=True, output=f"Created {path.name}.", data={"path": str(path)}
        )


# ---------------------------------------------------------------------- #
class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Delete a file. Requires explicit user confirmation."

    dangerous = True

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not path.exists():
            return ToolResult(ok=False, error=f"File not found: {path}")
        if path.is_dir():
            return ToolResult(ok=False, error="delete_file cannot delete directories.")

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.DELETE_FILE,
                target=str(path),
                reason="Delete file (irreversible)",
                dangerous=True,
            )
        )
        if decision != PermissionDecision.ALWAYS_ALLOW:
            return ToolResult(ok=False, error="Deletion cancelled by user.")

        try:
            path.unlink()
        except OSError as exc:
            return ToolResult(ok=False, error=f"Delete failed: {exc}")
        return ToolResult(
            ok=True, output=f"Deleted {path.name}.", data={"path": str(path)}
        )


# ---------------------------------------------------------------------- #
class MoveFileTool(Tool):
    name = "move_file"
    description = "Move or rename a file inside the workspace."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            src = ctx.workspace.resolve(arguments["source"])
            dst = ctx.workspace.resolve(arguments["destination"])
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not src.exists():
            return ToolResult(ok=False, error=f"Source not found: {src}")

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.MOVE_FILE,
                target=str(src),
                reason=f"Move to {dst}",
                details={"destination": str(dst)},
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied move.")

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            return ToolResult(ok=False, error=f"Move failed: {exc}")
        return ToolResult(ok=True, output=f"Moved {src.name} → {dst.name}.")


# ---------------------------------------------------------------------- #
class CopyFileTool(Tool):
    name = "copy_file"
    description = "Copy a file inside the workspace."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            src = ctx.workspace.resolve(arguments["source"])
            dst = ctx.workspace.resolve(arguments["destination"])
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not src.is_file():
            return ToolResult(ok=False, error=f"Source is not a file: {src}")

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.CREATE_FILE,
                target=str(dst),
                reason=f"Copy {src.name} → {dst.name}",
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied copy.")

        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
        except OSError as exc:
            return ToolResult(ok=False, error=f"Copy failed: {exc}")
        return ToolResult(ok=True, output=f"Copied {src.name} → {dst.name}.")


# ---------------------------------------------------------------------- #
class GetFileInfoTool(Tool):
    name = "get_file_info"
    description = "Return size, mtime, and type of a path."

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not path.exists():
            return ToolResult(ok=False, error=f"Path not found: {path}")
        st = path.stat()
        mtime = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        kind = "directory" if path.is_dir() else "file"
        output = (
            f"path: {path}\n"
            f"type: {kind}\n"
            f"size: {st.st_size} bytes\n"
            f"modified: {mtime}"
        )
        return ToolResult(
            ok=True, output=output, data={"size": st.st_size, "type": kind}
        )


# ---------------------------------------------------------------------- #
class ReplaceTextTool(Tool):
    name = "replace_text"
    description = (
        "Replace an exact substring inside a text file. "
        "Use this for surgical edits instead of rewriting the whole file."
    )

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old": {"type": "string", "description": "Exact text to find."},
                "new": {"type": "string", "description": "Replacement text."},
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Max replacements (default: all).",
                },
            },
            "required": ["path", "old", "new"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            path = ctx.workspace.resolve(arguments["path"])
            old = arguments["old"]
            new = arguments["new"]
        except (SecurityViolation, KeyError) as exc:
            return ToolResult(ok=False, error=str(exc))

        if not path.is_file():
            return ToolResult(ok=False, error=f"File not found: {path}")
        if not old:
            return ToolResult(ok=False, error="`old` string must not be empty.")

        original = _read_text(path)
        if original is None:
            return ToolResult(ok=False, error="Could not decode file.")

        occurrences = original.count(old)
        if occurrences == 0:
            return ToolResult(ok=False, error="`old` string was not found in the file.")

        count = arguments.get("count")
        if count is None or int(count) < 1:
            replaced = original.replace(old, new)
            applied = occurrences
        else:
            replaced = original.replace(old, new, int(count))
            applied = min(int(count), occurrences)

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.WRITE_FILE,
                target=str(path),
                reason=f"Replace text in {path.name}",
                details={"occurrences": applied},
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied text replacement.")

        backup = _make_backup(path)
        try:
            path.write_text(replaced, encoding="utf-8")
        except OSError as exc:
            return ToolResult(ok=False, error=f"Write failed: {exc}")
        return ToolResult(
            ok=True,
            output=f"Replaced {applied} occurrence(s) in {path.name}.",
            data={"applied": applied, "backup": str(backup) if backup else ""},
        )


# ---------------------------------------------------------------------- #
def _read_text(path: Path) -> str | None:
    for enc in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def _make_backup(path: Path) -> Path | None:
    """Create a `.bak` snapshot next to the file (only if it exists)."""
    if not path.exists() or not path.is_file():
        return None
    try:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        return backup
    except OSError:
        return None
