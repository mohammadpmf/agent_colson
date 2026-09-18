from __future__ import annotations

from pathlib import Path

import pytest

from app.security import SecurityViolation
from app.workspace import WorkspaceManager


def test_set_and_list(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('a')")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("print('b')")

    ws = WorkspaceManager(tmp_path)
    entries = ws.list_entries(".", depth=2)
    names = {Path(e.path).name for e in entries}
    assert "a.py" in names
    assert "b.py" in names


def test_resolve_inside(tmp_path: Path):
    (tmp_path / "x.txt").write_text("hi")
    ws = WorkspaceManager(tmp_path)
    resolved = ws.resolve("x.txt")
    assert resolved.name == "x.txt"


def test_resolve_outside_raises(tmp_path: Path):
    ws = WorkspaceManager(tmp_path)
    with pytest.raises(SecurityViolation):
        ws.resolve("../outside.txt")


def test_symlink_escape_blocked(tmp_path: Path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")
    ws = WorkspaceManager(tmp_path)
    with pytest.raises(SecurityViolation):
        ws.resolve("link.txt")


def test_binary_detection(tmp_path: Path):
    p = tmp_path / "blob.bin"
    p.write_bytes(b"\x00\x01\x02binary")
    ws = WorkspaceManager(tmp_path)
    assert ws.is_text_file(p) is False


def test_text_detection(tmp_path: Path):
    p = tmp_path / "hello.py"
    p.write_text("print('hello')")
    ws = WorkspaceManager(tmp_path)
    assert ws.is_text_file(p) is True
