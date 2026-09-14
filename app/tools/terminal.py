"""Terminal command execution tool."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

from app.permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
)

from .base import Tool, ToolContext, ToolResult

DEFAULT_TIMEOUT = 60
MAX_OUTPUT = 20_000


class RunCommandTool(Tool):
    name = "run_command"
    description = (
        "Execute a shell command inside the workspace root. "
        "Dangerous commands (rm -rf, format, shutdown, DROP DATABASE, ...) "
        "require an explicit confirmation."
    )

    dangerous = True @ property

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 600,
                    "default": DEFAULT_TIMEOUT,
                },
                "cwd": {"type": "string", "description": "Optional subdirectory."},
            },
            "required": ["command"],
        }

    def execute(self, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            command = arguments["command"]
            timeout = int(arguments.get("timeout", DEFAULT_TIMEOUT))
            cwd_arg = arguments.get("cwd", ".")
        except (KeyError, ValueError) as exc:
            return ToolResult(ok=False, error=f"Bad arguments: {exc}")

        try:
            cwd = ctx.workspace.resolve(cwd_arg)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"Invalid cwd: {exc}")

        guard = ctx.workspace.guard()
        try:
            guard.check_command(command)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=str(exc))

        dangerous = guard.is_dangerous_command(command)

        decision = ctx.permissions.check(
            PermissionRequest(
                action=PermissionAction.EXECUTE_COMMAND,
                target=command,
                reason="Execute terminal command",
                details={"cwd": str(cwd), "dangerous": dangerous},
                dangerous=dangerous,
            )
        )
        if decision == PermissionDecision.DENY:
            return ToolResult(ok=False, error="User denied command execution.")
        if dangerous and decision != PermissionDecision.ALWAYS_ALLOW:
            return ToolResult(
                ok=False,
                error="Dangerous command requires explicit Allow Once / Always Allow.",
            )

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")

        started = time.time()
        try:
            completed = subprocess.run(  # noqa: S602 — validated by guard
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                ok=False,
                error=f"Command timed out after {timeout}s.",
                data={"timeout": timeout},
            )
        except OSError as exc:
            return ToolResult(ok=False, error=f"Failed to launch command: {exc}")

        elapsed = time.time() - started
        stdout = _truncate(completed.stdout)
        stderr = _truncate(completed.stderr)
        output = (
            f"$ {command}\n"
            f"exit_code: {completed.returncode}\n"
            f"duration: {elapsed:.2f}s\n"
            f"--- stdout ---\n{stdout or '(empty)'}\n"
            f"--- stderr ---\n{stderr or '(empty)'}"
        )
        return ToolResult(
            ok=completed.returncode == 0,
            output=output,
            error=(
                ""
                if completed.returncode == 0
                else f"Non-zero exit code: {completed.returncode}"
            ),
            data={
                "exit_code": completed.returncode,
                "duration": elapsed,
                "stdout": stdout,
                "stderr": stderr,
            },
        )


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + f"\n... [truncated, {len(text) - MAX_OUTPUT} more chars]"
