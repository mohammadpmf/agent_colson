from __future__ import annotations

from pathlib import Path

import pytest

from app.permissions import (
    PermissionDecision,
    PermissionManager,
)
from app.permissions.storage import PermissionStorage
from app.tools import ToolContext, build_default_registry
from app.workspace import WorkspaceManager


@pytest.fixture()
def ctx(tmp_path: Path) -> ToolContext:
    ws = WorkspaceManager(tmp_path)
    storage = PermissionStorage(tmp_path / "perm.db")
    pm = PermissionManager(storage, tmp_path)
    pm.ask_callback = lambda req: PermissionDecision.ALWAYS_ALLOW
    return ToolContext(workspace=ws, permissions=pm)


def test_registry_has_expected_tools():
    reg = build_default_registry()
    for name in [
        "list_directory",
        "read_file",
        "write_file",
        "create_file",
        "delete_file",
        "move_file",
        "copy_file",
        "search_files",
        "search_text",
        "replace_text",
        "run_command",
        "get_file_info",
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
    ]:
        assert reg.get(name) is not None, f"missing tool: {name}"


def test_read_write_roundtrip(ctx: ToolContext):
    reg = build_default_registry()
    create = reg.get("create_file")
    read = reg.get("read_file")

    r1 = create.execute({"path": "hello.txt", "content": "hi there"}, ctx)
    assert r1.ok

    r2 = read.execute({"path": "hello.txt"}, ctx)
    assert r2.ok
    assert "hi there" in r2.output


def test_replace_text(ctx: ToolContext):
    reg = build_default_registry()
    reg.get("create_file").execute({"path": "a.py", "content": "x = 1"}, ctx)
    res = reg.get("replace_text").execute(
        {"path": "a.py", "old": "x = 1", "new": "x = 42"}, ctx
    )
    assert res.ok
    content = (ctx.workspace.root / "a.py").read_text()
    assert "x = 42" in content


def test_read_missing_file_fails(ctx: ToolContext):
    reg = build_default_registry()
    res = reg.get("read_file").execute({"path": "nope.py"}, ctx)
    assert res.ok is False
    assert "not found" in res.error.lower()


def test_delete_requires_dangerous(ctx: ToolContext):
    reg = build_default_registry()
    reg.get("create_file").execute({"path": "kill.txt", "content": "x"}, ctx)
    res = reg.get("delete_file").execute({"path": "kill.txt"}, ctx)
    # Our fixture uses ALWAYS_ALLOW, so delete succeeds
    assert res.ok
    assert not (ctx.workspace.root / "kill.txt").exists()


def test_search_text(ctx: ToolContext):
    reg = build_default_registry()
    reg.get("create_file").execute(
        {"path": "a.py", "content": "OrderStatus = 'NEW'"}, ctx
    )
    reg.get("create_file").execute({"path": "b.py", "content": "x = 1"}, ctx)
    res = reg.get("search_text").execute({"query": "OrderStatus"}, ctx)
    assert res.ok
    assert "a.py" in res.output
    assert "b.py" not in res.output


def test_run_command(ctx: ToolContext):
    reg = build_default_registry()
    res = reg.get("run_command").execute(
        {"command": "python -c \"print('hello')\""}, ctx
    )
    assert "hello" in res.output
