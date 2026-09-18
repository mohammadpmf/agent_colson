"""Permission manager – decides whether a tool action is allowed."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from .models import (
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
    PermissionRule,
    PermissionScope,
)
from .storage import PermissionStorage

log = logging.getLogger(__name__)


class PermissionManager:
    """Central authority for tool permission decisions.

    The GUI supplies a callback that displays a permission dialog and
    returns a `PermissionDecision`. Everything else is stored in SQLite.
    """

    def __init__(
        self,
        storage: PermissionStorage,
        workspace_root: Path,
        ask_callback: Callable[[PermissionRequest], PermissionDecision] | None = None,
    ) -> None:
        self.storage = storage
        self.workspace_root = Path(workspace_root).resolve()
        self.ask_callback = ask_callback

    # ------------------------------------------------------------------ #
    def set_workspace(self, workspace_root: Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def set_ask_callback(
        self, callback: Callable[[PermissionRequest], PermissionDecision] | None
    ) -> None:
        self.ask_callback = callback

    # ------------------------------------------------------------------ #
    def check(self, request: PermissionRequest) -> PermissionDecision:
        """Return the decision for a request, prompting the user if needed."""
        # 1) explicit rule match
        if not request.dangerous and self._has_rule(request.action, request.target):
            self.storage.log(
                request.action.value, request.target, "allowed_by_rule", request.reason
            )
            return PermissionDecision.ALWAYS_ALLOW

        # 2) need to ask
        if self.ask_callback is None:
            self.storage.log(
                request.action.value, request.target, "denied_no_ui", request.reason
            )
            return PermissionDecision.DENY

        decision = self.ask_callback(request)

        # 3) persist ALWAYS_ALLOW
        if decision == PermissionDecision.ALWAYS_ALLOW and not request.dangerous:
            scope = self._resolve_scope(request)
            target = self._scope_target(request, scope)
            self.storage.add_rule(
                PermissionRule(
                    action=request.action,
                    scope=scope,
                    target=target,
                    created_at=time.time(),
                )
            )

        self.storage.log(
            request.action.value,
            request.target,
            decision.value,
            request.reason,
        )
        return decision

    # ------------------------------------------------------------------ #
    def list_rules(self) -> list[PermissionRule]:
        return self.storage.list_rules()

    def reset_rules(self) -> None:
        self.storage.clear_rules()

    def audit_entries(self, limit: int = 200) -> list[dict]:
        return self.storage.audit_entries(limit)

    # ------------------------------------------------------------------ #
    def _has_rule(self, action: PermissionAction, target: str) -> bool:
        target_path = _norm(target)
        for rule in self.storage.list_rules():
            if rule.action != action:
                continue
            if rule.scope == PermissionScope.GLOBAL:
                return True
            if rule.scope == PermissionScope.WORKSPACE:
                if _norm(rule.target) == _norm(self.workspace_root) and _is_inside(self.workspace_root, target_path):
                    return True
            if rule.scope in (PermissionScope.FILE, PermissionScope.DIRECTORY):
                rule_path = _norm(rule.target)
                if rule.scope == PermissionScope.FILE and rule_path == target_path:
                    return True
                if rule.scope == PermissionScope.DIRECTORY and _is_inside(
                    rule_path, target_path
                ):
                    return True
        return False

    def _resolve_scope(self, request: PermissionRequest) -> PermissionScope:
        target = _norm(request.target)
        if _is_inside(self.workspace_root, target):
            return PermissionScope.WORKSPACE
        return PermissionScope.FILE

    def _scope_target(self, request: PermissionRequest, scope: PermissionScope) -> str:
        if scope == PermissionScope.WORKSPACE:
            return str(self.workspace_root)
        return _norm(request.target)


# ---------------------------------------------------------------------- #
def _norm(p: str | Path) -> str:
    try:
        return str(Path(p).expanduser().resolve())
    except OSError:
        return str(p)


def _is_inside(root: Path, candidate: str | Path) -> bool:
    try:
        root_r = Path(root).resolve()
        cand_r = Path(candidate).resolve()
        cand_r.relative_to(root_r)
        return True
    except (ValueError, OSError):
        return False
