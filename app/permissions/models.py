"""Permission data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionAction(str, Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    MOVE_FILE = "move_file"
    EXECUTE_COMMAND = "execute_command"
    NETWORK_ACCESS = "network_access"
    GIT_WRITE = "git_write"


class PermissionScope(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    WORKSPACE = "workspace"
    GLOBAL = "global"


class PermissionDecision(str, Enum):
    ALLOW_ONCE = "allow_once"
    DENY = "deny"
    ALWAYS_ALLOW = "always_allow"
    CANCEL = "cancel"


@dataclass
class PermissionRule:
    """A persisted `always allow` rule."""

    action: PermissionAction
    scope: PermissionScope
    target: str  # file path, dir path, workspace root, or "*"
    created_at: float = 0.0


@dataclass
class PermissionRequest:
    """An in-flight request presented to the user."""

    action: PermissionAction
    target: str
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    dangerous: bool = False
    scope: PermissionScope = PermissionScope.WORKSPACE
