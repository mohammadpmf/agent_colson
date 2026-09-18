from __future__ import annotations

from pathlib import Path

import pytest

from app.permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionManager,
    PermissionRequest,
)
from app.permissions.storage import PermissionStorage


@pytest.fixture()
def manager(tmp_path: Path) -> PermissionManager:
    storage = PermissionStorage(tmp_path / "perm.db")
    return PermissionManager(storage, workspace_root=tmp_path / "ws")


def test_allow_once_does_not_persist(manager: PermissionManager):
    manager.ask_callback = lambda req: PermissionDecision.ALLOW_ONCE
    decision = manager.check(
        PermissionRequest(action=PermissionAction.READ_FILE, target="/x/y.py")
    )
    assert decision == PermissionDecision.ALLOW_ONCE
    assert manager.list_rules() == []


def test_always_allow_persists_and_reuses(manager: PermissionManager, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "file.py"
    target.write_text("x")
    manager.set_workspace(ws)

    manager.ask_callback = lambda req: PermissionDecision.ALWAYS_ALLOW
    d1 = manager.check(
        PermissionRequest(action=PermissionAction.READ_FILE, target=str(target))
    )
    assert d1 == PermissionDecision.ALWAYS_ALLOW

    # Second time should short-circuit without asking
    manager.ask_callback = lambda req: pytest.fail("should not ask again")
    d2 = manager.check(
        PermissionRequest(action=PermissionAction.READ_FILE, target=str(target))
    )
    assert d2 == PermissionDecision.ALWAYS_ALLOW


def test_deny_does_not_persist(manager: PermissionManager):
    manager.ask_callback = lambda req: PermissionDecision.DENY
    decision = manager.check(
        PermissionRequest(action=PermissionAction.WRITE_FILE, target="/x/y.py")
    )
    assert decision == PermissionDecision.DENY
    assert manager.list_rules() == []


def test_no_callback_means_deny(manager: PermissionManager):
    decision = manager.check(
        PermissionRequest(action=PermissionAction.READ_FILE, target="/x/y.py")
    )
    assert decision == PermissionDecision.DENY
